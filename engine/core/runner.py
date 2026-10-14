"""scan → fix → write → re-scan → reconcile. One check failing never stops the run."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import rules
from .check import Check, Context
from .deck import Deck
from .edits import EditConflict, EditSession, FixRefused
from .findings import Change, Finding, Status

Emit = Callable[[dict], None]
PROBLEM = (Status.RED, Status.YELLOW)


def _noop(_event: dict) -> None:
    pass


@dataclass
class RunConfig:
    checks: set[str] | None = None   # None = each check's default_check
    fixes: set[str] | None = None    # None = each check's default_fix
    preset: str = "any"
    crew_fonts: set[str] = field(default_factory=set)
    layout: bool = False             # judge text as PowerPoint draws it (needs PowerPoint; slower)
    prefit_path: Path | None = None  # repair saves the deck here just before layout fixes (for per-slide undo)
    overrides: dict = field(default_factory=dict)   # threshold overrides from the app's Settings
    partial_export: str = "off"      # fit rounds 2+: export only changed slides ("off" | "check" | "on"), see _fit_pass

    def check_on(self, c: type[Check]) -> bool:
        return c.id in self.checks if self.checks is not None else c.default_check

    def fix_on(self, c: type[Check]) -> bool:
        if c.report_only or not self.check_on(c):
            return False
        return c.id in self.fixes if self.fixes is not None else c.default_fix


@dataclass
class Result:
    input_path: Path
    findings: list[Finding] = field(default_factory=list)
    clean_checks: list[str] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    output_path: Path | None = None
    notes: list[dict] = field(default_factory=list)     # tuning descriptions of layout fixes

    def summary(self) -> dict:
        problems = [f for f in self.findings if not f.informational]
        count = lambda s: sum(1 for f in problems if f.status == s)
        return {
            "type": "summary",
            "input": str(self.input_path),
            "output": str(self.output_path) if self.output_path else None,
            "green_fixed": count(Status.GREEN_FIXED),
            "yellow": sum(1 for f in problems if f.status == Status.YELLOW and not f.is_note),
            "notes": sum(1 for f in problems if f.is_note),
            "red": count(Status.RED),
            "tool_error": count(Status.TOOL_ERROR),
            "informational": sum(1 for f in self.findings if f.informational),
            "clean_checks": self.clean_checks,
            "changes": len(self.changes),
        }


def make_context(config: RunConfig) -> Context:
    return Context(thresholds={**rules.load("thresholds"), **config.overrides}, preset=config.preset,
                   crew_fonts={f.casefold() for f in config.crew_fonts})


_RENDERER = None


def _layout_for(deck, config: RunConfig):
    """A PowerPoint-backed layout for this exact deck file, or None (off, or PowerPoint missing)."""
    global _RENDERER
    if not config.layout:
        return None
    from ..render import PowerPointRenderer
    from .layout.pdf import PdfLayout
    ok, _ = PowerPointRenderer.available()      # asked every time: a hang switches it off mid-run
    if not ok:
        return None
    if _RENDERER is None:
        _RENDERER = PowerPointRenderer()
    return PdfLayout(deck, _RENDERER)


def _fit_pass(deck, fitters, edits, ctx, config, outcome, errors, emit):
    """Render the working copy, find layout problems, fix them, repeat (CLAUDE.md rule 6), then a final
    safety pass.

    One change per slide per round: every fix is judged against a fresh render of its slide (two fixes
    on one slide in the same round each checked against the other's OLD position: PAT 24).
    Safety pass (David 2026-10-10): render the result once more; any slide that is now worse than
    before the layout fixes (text off the slide, text over text, words hidden behind a picture, a
    header with more lines) goes back to how it was. "Ugly but serviceable" must never become broken.
    """
    import tempfile
    from copy import deepcopy
    if _layout_for(deck, config) is None:
        return
    from .layout.pdf import PdfLayout
    rounds = int(ctx.thresholds.get("fit_max_rounds", 3))
    fit_ids = {c.id for c in fitters}
    edits.allow_refining(fit_ids)
    snapshots = {n: deepcopy(slide._element) for n, slide in enumerate(deck.slides, 1)}
    first_change = len(edits.changes)
    # Per-box attempt limit (optimization round 2026-10-11): if a box still has the same problem after
    # `fit_max_attempts_per_box` changes, PowerPoint isn't wrapping as predicted; put the box back as
    # it was before the first attempt and stop, so a repair settles and a second repair changes nothing.
    max_attempts = int(ctx.thresholds.get("fit_max_attempts_per_box", 2))
    attempts: dict[tuple, list] = {}        # finding key → [(seq, shape XML before, changes made)]
    gave_up: set[tuple] = set()
    seq = 0
    import time
    # Hard time budget (David 2026-10-11: "55 minutes on one deck is insane"): after it, no new fix
    # attempts start; findings are still detected and the safety check still runs.
    deadline = time.monotonic() + float(ctx.thresholds.get("fit_time_budget_s", 120))
    out_of_time = False
    dirty: set[int] | None = None           # rounds 2+: the slides the previous round changed
    seen_all: dict[int, set] = {}           # latest layout problems per slide (unchanged slides keep theirs)
    from .content import is_hidden
    visible = sum(1 for s in deck.slides if not is_hidden(s))
    prev_layout = None
    export_times: list[tuple[int, float, int]] = []     # (round, export seconds, slides changed)
    from ..render import RenderError
    try:
        with tempfile.TemporaryDirectory() as tmp:
            prefit = None
            for rnd in range(1, rounds + 1):
                emit({"type": "progress", "stage": "fit", "round": rnd, "rounds": rounds})
                work = Path(tmp) / f"round{rnd}.pptx"
                deck.save(work, render_copy=True)
                partial = _partial_ok(config, ctx, dirty, prev_layout, visible)
                layout = PdfLayout(deck, _RENDERER, path=work, only=dirty if partial else None,
                                   base=prev_layout if partial else None, check=config.partial_export == "check")
                prefit = prefit or layout
                rctx = replace(ctx, layout=layout, only_slides=frozenset(dirty) if dirty is not None else None)
                touched, did = set(), False
                seen: dict[int, set] = {}       # this round's layout problems by slide (see below)
                for cls in fitters:
                    check = cls()
                    edits.begin(cls)
                    found = check.detect(deck, rctx)
                    if dirty is not None:       # a slide no fix touched last round has nothing new to find
                        found = [f for f in found if f.slide in dirty]
                    for f in found:
                        if not f.informational and f.status in PROBLEM:
                            seen.setdefault(f.slide, set()).add((f.check_id, f.shape_id, f.subject))
                    for f in found:
                        if f.informational or f.status not in PROBLEM or f.slide in touched:
                            continue
                        key = (f.check_id, f.slide, f.shape_id, f.subject)
                        if key in gave_up:
                            continue
                        if time.monotonic() > deadline:
                            if not out_of_time:
                                emit({"type": "warn", "message": "Layout fixes hit their time limit; what's left is "
                                                                 "listed to check by hand."})
                            out_of_time = True
                            outcome.setdefault(f.key, ("refused", "layout fixing ran out of time before this one"))
                            continue
                        if len(attempts.get(key, [])) >= max_attempts:
                            _give_up_box(deck, edits, attempts, key)
                            gave_up.add(key)
                            outcome[f.key] = ("refused", "PowerPoint didn't re-wrap the text as predicted, "
                                                         "so this box was left as it was")
                            touched.add(f.slide)
                            did = True
                            continue
                        if _shared_id(deck, f):
                            outcome[f.key] = ("refused", SHARED_ID)
                            continue
                        sv = deck.find_shape(f.slide, f.shape_id) if f.shape_id is not None else None
                        shape_before = deepcopy(sv.shape.element) if sv is not None else None
                        n = len(edits.changes)
                        try:
                            check.fix(deck, f, edits, rctx)
                            outcome[f.key] = ("attempted", "")
                        except FixRefused as e:
                            outcome.setdefault(f.key, ("refused", str(e)))
                        except EditConflict as e:
                            outcome[f.key] = ("conflict", str(e))
                        except Exception as e:  # noqa: BLE001
                            outcome[f.key] = ("failed", str(e))
                            errors.append(Finding(cls.id, Status.TOOL_ERROR, f"{cls.title} fix couldn't run: {e}",
                                                  slide=f.slide, shape_id=f.shape_id, shape_name=f.shape_name,
                                                  subject=f.subject, evidence={"exception": type(e).__name__}))
                        if len(edits.changes) > n:
                            touched.add(f.slide)
                            did = True
                            seq += 1
                            attempts.setdefault(key, []).append((seq, shape_before, edits.changes[n:]))
                for n in (dirty if dirty is not None else range(1, len(deck.slides) + 1)):
                    seen_all[n] = seen.get(n, set())
                _partial_report(layout, rnd, dirty, visible, partial, export_times, emit)
                prev_layout = layout
                if not did:
                    settled = (layout, {n: p for n, p in seen_all.items() if p})
                    break
                if out_of_time:
                    settled = None
                    break
                dirty = set(touched)
            else:
                settled = None
            _partial_hint(config, ctx, export_times, visible, emit)
            if len(edits.changes) == first_change or prefit is None:
                return
            emit({"type": "progress", "stage": "safety"})
            problems: dict[int, dict[int, set]] = {}     # id(layout) → slide → problems, one detect() per render
            if settled:
                # The last round changed nothing, so the deck is exactly what that round rendered and
                # checked: reuse its render and findings instead of saving, rendering and detecting again.
                final, problems[id(settled[0])] = settled
            else:
                final_path = Path(tmp) / "final.pptx"
                deck.save(final_path, render_copy=True)
                final = PdfLayout(deck, _RENDERER, path=final_path)
            changed = {c.slide for c in edits.changes[first_change:] if c.slide} | {
                n for n, slide in enumerate(deck.slides, 1)
                if any(c.part == str(slide.part.partname) for c in edits.changes[first_change:])}
            for n in sorted(changed):
                pre, post = _health(deck, prefit, n, ctx), _health(deck, final, n, ctx)
                worse = [label for label, a, b in (("text off the slide", pre.off, post.off),
                                                   ("text over text", pre.collisions, post.collisions),
                                                   ("words hidden behind a picture", pre.hidden, post.hidden),
                                                   ("a header gained a line", pre.header_excess, post.header_excess))
                         if b > a]
                if worse:
                    _revert_slide(deck, n, snapshots[n], edits, fit_ids, outcome, ", ".join(worse))
                elif not (_fit_problems(deck, fitters, prefit, ctx, n, problems)
                          - _fit_problems(deck, fitters, final, ctx, n, problems)):
                    # David 2026-10-10 (CLARB 11): six width nudges, orphan still there. A change that fixed
                    # nothing isn't worth a review box; put the slide back without a word.
                    _revert_slide(deck, n, snapshots[n], edits, fit_ids, outcome, None)

    except Exception as e:  # noqa: BLE001
        # PowerPoint failed partway (on Windows: stopped responding), or the fit pass itself broke (a
        # parse error, a bug). Nothing after this point was checked by a render, so every layout change
        # goes back; the other fixes stand. Only PowerPoint's own failures are "skipped"; anything else
        # is a tool_error so it gets noticed.
        if isinstance(e, RenderError):
            emit({"type": "warn", "message": f"Layout fixes skipped: {e}"})
        else:
            emit({"type": "warn", "message": f"Layout fixes were undone: the fitting step failed ({type(e).__name__}: {e})"})
            errors.append(Finding("L000", Status.TOOL_ERROR, f"Layout fixing failed and was undone: {type(e).__name__}: {e}",
                                  evidence={"exception": type(e).__name__}))
        fit_changes = [c for c in edits.changes[first_change:] if c.check_id in fit_ids]
        changed = {c.slide for c in fit_changes if c.slide} | {
            n for n, slide in enumerate(deck.slides, 1) if any(c.part == str(slide.part.partname) for c in fit_changes)}
        for n in sorted(changed):
            _revert_slide(deck, n, snapshots[n], edits, fit_ids, outcome, None,
                          why=f"PowerPoint stopped before this fix could be checked ({e}), so the slide was left as it was")


SHARED_ID = ("two shapes on this slide share this shape's id (slides merged from two decks do this), so SlideTistic "
             "can't tell which one to change; fix it by hand")


def _shared_id(deck, f) -> bool:
    """The finding's shape id belongs to more than one shape on its slide: a fix could change the wrong one
    (adversarial round 1). Both are left alone and reported."""
    if f.slide is None or f.shape_id is None:
        return False
    return sum(1 for sv in deck.slide_shapes(f.slide) if sv.shape_id == f.shape_id) > 1


def _partial_ok(config, ctx, dirty, prev_layout, visible) -> bool:
    """Export only the changed slides this round? Opt-in, rounds 2+, and only when the first export was slow
    and few slides changed (David 2026-10-13: big decks are big from media, which stand-ins already shrink)."""
    if config.partial_export == "off" or dirty is None or prev_layout is None or not visible:
        return False
    first = prev_layout
    while first.base is not None:
        first = first.base
    slow = (first.export_s or 0) >= float(ctx.thresholds.get("partial_export_min_export_s", 20))
    few = len(dirty) <= visible * float(ctx.thresholds.get("partial_export_max_changed_pct", 25)) / 100
    return slow and few


def _partial_report(layout, rnd, dirty, visible, partial, export_times, emit) -> None:
    changed = len(dirty) if dirty is not None else visible
    export_times.append((rnd, layout.export_s or 0.0, changed))
    if partial and layout.partial_mismatch is not None:
        emit({"type": "partial_export", "round": rnd, "changed": sorted(dirty), "mismatch": layout.partial_mismatch})
        if layout.partial_mismatch:
            emit({"type": "warn", "message": f"Changed-slide export (check mode) disagreed with the full export on "
                                             f"slide(s) {', '.join(map(str, layout.partial_mismatch))}; the full "
                                             "export was used. Tell David."})


def _partial_hint(config, ctx, export_times, visible, emit) -> None:
    """Changed-slide export is off: say how much it would have saved on this repair, when that's a lot. Every
    round after the first drew the whole deck; drawing only its changed slides costs about their share."""
    if config.partial_export != "off" or len(export_times) < 2 or not visible:
        return
    first_s = export_times[0][1]
    if first_s < float(ctx.thresholds.get("partial_export_min_export_s", 20)):
        return
    # Every export also pays a fixed start-up (opening the copy, PDF setup): ~3 s measured on CLARB MASTER, where
    # the plain per-slide share said 38 s and the real saving was 22 s (2026-10-13).
    fixed = float(ctx.thresholds.get("partial_export_overhead_s", 3))
    per_slide = max(0.0, first_s - fixed) / visible
    saving = sum(max(0.0, s - fixed - per_slide * changed) for _, s, changed in export_times[1:])
    if saving >= float(ctx.thresholds.get("partial_export_hint_min_saving_s", 30)):
        emit({"type": "partial_export_hint", "seconds": round(saving), "first_export_s": round(first_s, 1),
              "rounds": len(export_times)})


def _give_up_box(deck, edits, attempts: dict, key: tuple) -> None:
    """Put a box back the way it was before `key`'s first fix attempt, and drop the logged changes of
    every layout attempt on that box since then (other checks' later changes to it are undone too)."""
    _, slide, sid, _ = key
    first_seq, before_el, _ = attempts[key][0]
    sv = deck.find_shape(slide, sid)
    if sv is not None and before_el is not None:
        from copy import deepcopy
        el = sv.shape.element
        el.getparent().replace(el, deepcopy(before_el))
        deck.invalidate()
    drop = set()
    for k in list(attempts):
        if k[1] == slide and k[2] == sid:
            kept = [a for a in attempts[k] if a[0] < first_seq]
            drop |= {id(c) for a in attempts[k] if a[0] >= first_seq for c in a[2]}
            if kept:
                attempts[k] = kept
            else:
                del attempts[k]
    edits.changes[:] = [c for c in edits.changes if id(c) not in drop]


def _fit_problems(deck, fitters, layout, ctx, n, cache: dict | None = None) -> set:
    """The layout problems on slide n according to this render: {(check id, shape id, subject)}.

    With `cache`, every check runs once per render and the result is kept per slide: the safety pass
    asked again for each changed slide, re-running every check over the whole deck each time (PAT 23,
    Windows 2026-10-10: 265 of 453 s). A slide's layout findings come from that slide's own shapes and
    render, and reverting a slide only changes that slide, so the answers are the same."""
    if cache is None or id(layout) not in cache:
        rctx = replace(ctx, layout=layout)
        by_slide: dict[int, set] = {}
        for cls in fitters:
            for f in cls().detect(deck, rctx):
                if not f.informational and f.status in PROBLEM:
                    by_slide.setdefault(f.slide, set()).add((f.check_id, f.shape_id, f.subject))
        if cache is None:
            return by_slide.get(n, set())
        cache[id(layout)] = by_slide
    return cache[id(layout)].get(n, set())


@dataclass
class _Health:
    off: int = 0
    collisions: int = 0
    hidden: int = 0
    header_excess: int = 0


def _health(deck, layout, n, ctx) -> _Health:
    """What PowerPoint actually drew on slide n: text off the slide, text over text, words behind a
    picture that sits above them, and header lines beyond the original deck's."""
    from . import fit
    slide_layout = layout.slide(n)
    W, H, tol = deck.slide_width, deck.slide_height, 12700
    h = _Health()
    # Letters, not boxes (review 2026-10-13, 1.6): the same rules as L008/L010. A line box past an edge
    # counts only if the picture shows letters touching that edge; two colliding lines count only if the
    # picture doesn't show a clean row between them. Without a picture, the boxes decide (as before).
    cut_off = getattr(layout, "cut_off", None)
    apart = getattr(layout, "letters_apart", None)
    for st in slide_layout.values():
        for l in st.lines:
            edges = [e for e, out in (("left", l.left < -tol), ("top", l.top < -tol), ("right", l.right > W + tol),
                                      ("bottom", l.bottom > H + tol)) if out]
            if edges and (cut_off is None or any(cut_off(n, l, e) is not False for e in edges)):
                h.off += 1
    # Words PowerPoint didn't draw at all count too: Mac PowerPoint leaves text that's fully off the
    # slide out of the PDF, so a box shoved off the slide (or shrunk to nothing) has no lines to count
    # (app run 2026-10-11: every lower-thirds slide lost its text and the old count saw nothing wrong).
    from .content import shape_text
    from .layout.pdf import _tokens
    for sv in deck.slide_shapes(n):
        if sv.text_bearing:
            st = slide_layout.get(sv.shape_id)
            drawn = sum(len(l.tokens) for l in st.lines) if st else 0
            h.off += max(0, len(_tokens(shape_text(sv.shape))) - drawn)
    items = [st for st in slide_layout.values() if st.lines]
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if any(fit.lines_collide(la, lb, 2 * 12700) and not (apart and apart(n, la, lb))
                   for la in a.lines for lb in b.lines):
                h.collisions += 1
    shapes = deck.slide_shapes(n)
    z = {sv.shape_id: i for i, sv in enumerate(shapes)}
    pics = [(z[sv.shape_id], sv.bounds) for sv in shapes if fit.is_graphic(sv)]
    for sid, st in slide_layout.items():
        for l in st.lines:
            for w in l.boxes:
                cx, cy = (w.left + w.right) / 2, (l.top + l.bottom) / 2
                if any(zi > z.get(sid, -1) and b.left <= cx <= b.right and b.top <= cy <= b.bottom for zi, b in pics):
                    h.hidden += 1
    for sid, st in slide_layout.items():
        sv = deck.find_shape(n, sid)
        was = ctx.baseline_lines.get((n, sid))
        if sv and was is not None and fit.is_header(deck, sv, slide_layout):
            h.header_excess += max(0, len(st.lines) - was)
    return h


def _revert_slide(deck, n, snapshot, edits, fit_ids, outcome, reason, why=None):
    """Put slide n back the way it was before the layout fixes, and record why. reason None: the fixes
    simply didn't work, so the slide is restored quietly (no review entry)."""
    from copy import deepcopy
    slide = deck.slides[n - 1]
    el = slide._element
    for child in list(el):
        el.remove(child)
    for child in deepcopy(snapshot):
        el.append(child)
    deck.invalidate()
    partname = str(slide.part.partname)
    edits.changes[:] = [c for c in edits.changes
                        if not (c.check_id in fit_ids and (c.slide == n or c.part == partname))]
    if reason:
        edits.changes.append(Change("SAFETY", n, None, None, "layout fixes undone", reason, "slide kept as it was"))
    why = why or (f"undone by the final safety check: the fixes made {reason} worse" if reason
                  else "PowerPoint didn't re-wrap the text as predicted, so the slide was left as it was")
    for key, (kind, _) in list(outcome.items()):
        if key[0] in fit_ids and key[1] == n:
            outcome[key] = ("refused", why)


def cleanup():
    """Remove the layout renderer's work files (PowerPoint copies and PDFs)."""
    global _RENDERER
    if _RENDERER is not None:
        _RENDERER.cleanup()
        _RENDERER = None


def detect_all(deck: Deck, checks: list[type[Check]], config: RunConfig, ctx: Context,
               emit: Emit = _noop, layout=None) -> tuple[list[Finding], list[str]]:
    ctx = replace(ctx, layout=layout or _layout_for(deck, config))
    findings, clean = [], []
    enabled = [c for c in checks if config.check_on(c)]
    for n, cls in enumerate(enabled, 1):
        emit({"type": "progress", "stage": "scan", "check": cls.id, "index": n, "total": len(enabled)})
        try:
            found = cls().detect(deck, ctx)
        except Exception as e:  # noqa: BLE001 — a broken check becomes a report entry, not a crash
            found = [Finding(cls.id, Status.TOOL_ERROR, f"{cls.title} couldn't run: {e}",
                             evidence={"exception": type(e).__name__})]
        findings.extend(found)
        if not found:
            clean.append(cls.id)
    return findings, clean


def scan(path, checks: list[type[Check]], config: RunConfig, emit: Emit = _noop) -> Result:
    path = Path(path)
    deck = Deck(path)
    findings, clean = detect_all(deck, checks, config, make_context(config), emit)
    result = Result(input_path=path, findings=findings, clean_checks=clean)
    for f in findings:
        emit({"type": "finding", **f.to_dict()})
    emit(result.summary())
    return result


def output_path_for(input_path: Path, out_dir: Path | None = None, suffix: str = " - mended") -> Path:
    """Never overwrites: 'Deck - mended.pptx', then 'Deck - mended (2).pptx', …"""
    folder = Path(out_dir) if out_dir else input_path.parent
    candidate = folder / f"{input_path.stem}{suffix}.pptx"
    n = 2
    while candidate.exists():
        candidate = folder / f"{input_path.stem}{suffix} ({n}).pptx"
        n += 1
    return candidate


def repair(path, checks: list[type[Check]], config: RunConfig, out_path: Path | None = None,
           emit: Emit = _noop) -> Result:
    path = Path(path)
    ctx = make_context(config)
    original = Deck(path)
    base_layout = _layout_for(original, config)
    if base_layout is not None:
        # Line counts in the ORIGINAL deck: headers must never end up with more (L001, safety pass).
        # A box with no matched lines in the original render is "unknown", not "zero lines" (PAT 26).
        from ..render import RenderError
        try:
            ctx = replace(ctx, baseline_lines={(n, sid): len(st.lines)
                                               for n in range(1, len(original.slides) + 1)
                                               for sid, st in base_layout.slide(n).items() if st.lines})
        except RenderError as e:
            # PowerPoint couldn't draw the original: carry on as on a machine without PowerPoint.
            emit({"type": "warn", "message": f"Layout fixes skipped: {e}"})
            config, base_layout = replace(config, layout=False), None
    before, _ = detect_all(original, checks, config, ctx, emit, layout=base_layout)

    # Fix in dependency order, re-detecting each check on the working deck so earlier
    # fixes (fonts) are reflected in later checks' findings (geometry, layout).
    deck = Deck(path)
    edits = EditSession(deck)
    outcome: dict[tuple, tuple[str, str]] = {}   # finding key → (kind, detail)
    errors: list[Finding] = []
    fixers = [c for c in checks if config.fix_on(c)]
    # Layout fixes need a fresh PowerPoint render after every change; they run last, in rounds.
    fitters = [c for c in fixers if "layout" in c.requires]
    fixers = [c for c in fixers if "layout" not in c.requires]
    for n, cls in enumerate(fixers, 1):
        emit({"type": "progress", "stage": "fix", "check": cls.id, "index": n, "total": len(fixers)})
        check = cls()
        edits.begin(cls)
        try:
            current = check.detect(deck, ctx)
        except Exception:  # noqa: BLE001 — already reported as tool_error by the first scan
            continue
        for f in current:
            if f.informational or f.status not in PROBLEM:
                continue
            if _shared_id(deck, f):
                outcome[f.key] = ("refused", SHARED_ID)
                continue
            try:
                check.fix(deck, f, edits, ctx)
                outcome[f.key] = ("attempted", "")
            except FixRefused as e:
                outcome[f.key] = ("refused", str(e))
            except EditConflict as e:
                outcome[f.key] = ("conflict", str(e))
            except Exception as e:  # noqa: BLE001
                outcome[f.key] = ("failed", str(e))
                errors.append(Finding(cls.id, Status.TOOL_ERROR, f"{cls.title} fix couldn't run: {e}",
                                      slide=f.slide, shape_id=f.shape_id, shape_name=f.shape_name,
                                      subject=f.subject, evidence={"exception": type(e).__name__}))

    if config.prefit_path:
        # Media as stand-ins: undo-slide only copies slide XML from it, and a 500 MB deck's review bundle
        # shouldn't hold a second 500 MB copy (review 2026-10-13).
        deck.save(config.prefit_path, render_copy=True)
    if fitters:
        _fit_pass(deck, fitters, edits, ctx, config, outcome, errors, emit)

    target = Path(out_path) if out_path else output_path_for(path)
    if target.resolve() == path.resolve():
        raise ValueError("Refusing to overwrite the input file")
    out = deck.save(target)
    from . import invariants
    for problem in invariants.broken(path, out):
        # Never expected: a fix went wrong. Said loudly (a tool_error) rather than handing over a deck that lost
        # a word or a shape.
        errors.append(Finding("X000", Status.TOOL_ERROR, f"Repair broke a promise: {problem}. Check this deck by "
                              "hand and tell David.", evidence={"invariant": problem}))
        emit({"type": "warn", "message": f"Repair check failed: {problem}"})
    emit({"type": "progress", "stage": "rescan"})
    after, clean = detect_all(Deck(out), checks, config, ctx)

    findings = _reconcile(before, after, outcome, edits.changes) + errors
    result = Result(input_path=path, findings=findings, clean_checks=clean,
                    changes=edits.changes, output_path=out, notes=edits.notes)
    for c in edits.changes:
        emit({"type": "change", **c.to_dict()})
    for f in findings:
        emit({"type": "finding", **f.to_dict()})
    emit(result.summary())
    return result


def _deck_wide_culprit(changes) -> str | None:
    """Deck-wide edits (font renames) have no shape; name the checks that made them."""
    ids = sorted({c.check_id for c in changes if c.shape_id is None})
    return ", ".join(ids) or None


def _reconcile(before, after, outcome, changes) -> list[Finding]:
    after_by_key = {f.key: f for f in after}
    before_keys = {f.key for f in before}
    out: list[Finding] = []

    for f in before:
        if f.informational or f.status == Status.TOOL_ERROR:
            continue   # informational: the re-scan's copy is used; tool errors: re-scan reports them again
        kind, detail = outcome.get(f.key, ("off", ""))
        still = after_by_key.get(f.key)
        if still is None:
            f.status = Status.GREEN_FIXED
        elif kind == "attempted":
            # Keeps the re-scan's own severity (David 2026-10-10: a title still near the edge is ugly,
            # not broken); red stays for what the check itself calls red.
            still.evidence["fix_result"] = "fix ran but the problem is still there"
            f = still
        elif kind in ("refused", "conflict"):
            if kind == "conflict":
                still.status = Status.YELLOW
            still.evidence["fix_result"] = f"{kind}: {detail}"
            f = still
        else:
            f = still
        out.append(f)

    touched_by = {(c.slide, c.shape_id): c.check_id for c in changes}
    for f in after:
        if f.key in before_keys and not f.informational and f.status != Status.TOOL_ERROR:
            continue
        if not f.informational and f.status in PROBLEM:
            # Keep the check's own severity (David 2026-10-10: an orphan caused by a font fix is
            # "needs a look", text pushed off the slide is still red) and say what caused it.
            culprit = touched_by.get((f.slide, f.shape_id)) or _deck_wide_culprit(changes)
            f.evidence["introduced_by"] = culprit or "appeared after repair"
        out.append(f)
    return out
