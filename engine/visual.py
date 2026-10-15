"""Visual review: which shapes changed, where to draw boxes, and the before/after images."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .core import Deck, Status
from .core.content import is_hidden
from .core.shapes import PICTURE, GROUP


KIND = {"F": "font", "G": "placement", "L": "layout", "M": "media", "P": "media", "C": "content", "X": "content"}
KIND_LABEL = {"font": "Font fix", "placement": "Placement", "layout": "Layout fit", "media": "Media & playback",
              "content": "Content"}
TIERS = {1: "Broken: fix before the show", 2: "Changes SlideTistic made: check them",
         3: "Needs a look", 4: "Changed underneath, looks identical", 5: "Notes: low priority"}


def kind_of(check_id: str) -> str:
    return KIND.get(check_id[:1], "content")


@dataclass
class Box:
    left: float      # % of slide width/height
    top: float
    width: float
    height: float
    label: str       # what happened, one line
    kind: str        # font | placement | layout | media | content  (box colour)
    mode: str        # changed | red | yellow | note                   (line style / severity)
    detail: str = "" # diagnostic: the rule and numbers behind it


@dataclass
class SlideVisual:
    slide: int
    before_boxes: list[Box] = field(default_factory=list)
    after_boxes: list[Box] = field(default_factory=list)
    before_png: str | None = None    # data: URI
    after_png: str | None = None
    looks_same: bool = False         # rendered before/after are visually identical
    media: list = field(default_factory=list)   # video/audio on the slide: the review's ▶ VIDEO badges
    tuning: list = field(default_factory=list)  # per changed shape: what the change was, in numbers (core/tuning.py)
    tuning_sig: str = ""             # identifies this exact set of changes (a vote applies to it)
    diff_pct: float | None = None    # share of the slide's pixels the change visibly altered

    @property
    def tier(self) -> int:
        modes = {b.mode for b in self.after_boxes + self.before_boxes}
        if "red" in modes:
            return 1
        if not self.looks_same and any(b.mode == "changed" for b in self.after_boxes):
            return 2
        if "yellow" in modes:
            return 3
        if "note" in modes and not any(b.mode == "changed" for b in self.after_boxes):
            return 5
        return 4

    @property
    def needs_eyes(self) -> bool:
        return self.tier < 4


def changed_shapes(original: Path, mended: Path) -> dict[tuple[int, int], tuple]:
    """(slide, shape id) → (before ShapeView, after ShapeView) for every shape whose XML differs."""
    before = {(s.slide_number, s.shape_id): s for s in Deck(original).iter_shapes() if s.kind != GROUP}
    after = {(s.slide_number, s.shape_id): s for s in Deck(mended).iter_shapes() if s.kind != GROUP}
    return {k: (before[k], after[k]) for k in before.keys() & after.keys()
            if etree.tostring(before[k].shape.element) != etree.tostring(after[k].shape.element)}


def plan(result, original: Path, mended: Path | None) -> list[SlideVisual]:
    """Every slide worth a look, with boxes: changed shapes (before + after) and open findings (current)."""
    current = Deck(mended or original)
    W, H = current.slide_width, current.slide_height
    visuals: dict[int, SlideVisual] = {}

    def pct(l, t, r, b) -> tuple[float, float, float, float]:
        return 100 * l / W, 100 * t / H, 100 * (r - l) / W, 100 * (b - t) / H

    def from_sv(sv):
        bd = sv.bounds
        return pct(bd.left, bd.top, bd.right, bd.bottom)

    if mended:
        per_shape: dict[tuple, list] = {}
        for c in result.changes:
            if c.slide and c.shape_id:
                per_shape.setdefault((c.slide, c.shape_id), []).append(c)
        fixed = {f.key: f for f in result.findings if f.status == Status.GREEN_FIXED}
        deck_fixes = [f for f in fixed.values() if not f.slide]
        for (slide, sid), (b, a) in changed_shapes(original, mended).items():
            changes = per_shape.get((slide, sid), [])
            if not changes and PICTURE in (getattr(b, "kind", None), getattr(a, "kind", None)):
                # A picture changed only by a deck-wide fix is Compress pictures (M013): smaller file, same look by
                # design, reported by its own banner. Not a slide to check or vote on (David 2026-10-15: 22 votes
                # "not worth it").
                continue
            if changes:
                cid = changes[0].check_id
                label = _change_label(changes)
                rule = next((f.evidence.get("rule", "") for f in fixed.values()
                             if f.slide == slide and f.shape_id == sid), "")
            else:   # touched by a deck-wide fix (font renames, embedded list)
                cid = deck_fixes[0].check_id if deck_fixes else "F"
                label = "Deck-wide fix: " + ", ".join(f"{f.check_id} {f.subject}" for f in deck_fixes[:4])
                rule = " | ".join(f"{f.check_id}: {f.evidence.get('rule', f.message)}" for f in deck_fixes[:4])
            v = visuals.setdefault(slide, SlideVisual(slide))
            v.tuning.append(_net_change(slide, sid, b, a, changes, getattr(result, "notes", [])))
            if b.bounds:
                v.before_boxes.append(Box(*from_sv(b), label, kind_of(cid), "changed", rule))
            if a.bounds:
                v.after_boxes.append(Box(*from_sv(a), label, kind_of(cid), "changed", rule))

    shapes = {(s.slide_number, s.shape_id): s for s in current.iter_shapes()}
    for f in result.findings:
        if f.status not in (Status.RED, Status.YELLOW) or not f.slide or f.informational:
            continue            # information (an add-in's slide) draws no box and puts no slide in a tier
        if "box_emu" in f.evidence:            # layout checks outline the drawn text itself
            geom = pct(*f.evidence["box_emu"])
        elif f.shape_id and (f.slide, f.shape_id) in shapes and shapes[(f.slide, f.shape_id)].bounds:
            geom = from_sv(shapes[(f.slide, f.shape_id)])
        else:
            continue
        v = visuals.setdefault(f.slide, SlideVisual(f.slide))
        target = v.after_boxes if mended else v.before_boxes
        target.append(Box(*geom, f"{f.check_id}: {f.message}", kind_of(f.check_id), "note" if f.is_note else f.status.value,
                          f.evidence.get("rule", "")))
    # Badge every video and sound on the slides shown, so operators see at a glance where media plays
    # (David 2026-10-11: media is the biggest pre-show job).
    from .core.media import media_items
    starts = {"automatic": "plays automatically", "click_sequence": "starts on click {clicks}",
              "on_click": "only when clicked", "no_timing": "no start setting", "unknown": "start unclear"}
    for m in media_items(current):
        sv = shapes.get((m.slide, m.shape_id))
        if m.slide in visuals and sv is not None and sv.bounds:
            l, t, w, h = from_sv(sv)
            visuals[m.slide].media.append({"left": l, "top": t, "width": w, "height": h, "kind": m.kind,
                                           "start": starts.get(m.mode, "").format(clicks=m.clicks),
                                           "linked": m.linked})
    for v in visuals.values():
        if v.tuning:
            v.tuning.sort(key=lambda t: t["shape_id"])
            v.tuning_sig = hashlib.sha1(json.dumps(v.tuning, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return [visuals[k] for k in sorted(visuals)]


def _net_change(slide, sid, b, a, changes, notes) -> dict:
    """What David sees for one changed shape, in tuning features: the planned-fix description (trigger, role,
    kind) with the sizes replaced by the NET before → after difference (a box may have had two attempts)."""
    from .core import EMU_PER_INCH, tuning
    kept = [n["features"] for n in notes if n["slide"] == slide and n["shape_id"] == sid and not n.get("gate")]
    if not kept:
        cid = changes[0].check_id if changes else None
        return {"shape_id": sid, "check": cid, "fix": "other",
                "props": sorted({c.prop for c in changes}) or ["deck-wide"]}
    f = dict(kept[-1])
    font = spacing = 1.0
    for k in kept:
        font *= 1 - k.get("font_pct", 0) / 100
        spacing *= 1 - k.get("spacing_pct", 0) / 100
    if b.bounds and a.bounds:
        dx, dy = a.bounds.left - b.bounds.left, a.bounds.top - b.bounds.top
        f["move_in"] = round(math.hypot(dx, dy) / EMU_PER_INCH, 3)
        f["width_pct"] = round((a.bounds.width / b.bounds.width - 1) * 100, 1) if b.bounds.width else 0.0
    f["font_pct"], f["spacing_pct"] = round((1 - font) * 100, 1), round((1 - spacing) * 100, 1)
    if f.get("fix") not in ("push", "pair"):
        f["fix"] = tuning.fix_kind(font=font, spacing=spacing, width_pct=f.get("width_pct", 0))
    f["attempts"] = len(kept)
    f["shape_id"] = sid
    return f


def render(visuals: list[SlideVisual], original: Path, mended: Path, renderer, image_dir: Path | None = None) -> None:
    """Fill in before/after images. PowerPoint's PDF leaves out hidden slides, so map numbers to pages.
    With `image_dir`, images are written there as files (the app's review bundle) and the visuals hold
    their file names; otherwise they're embedded as data: URIs (the stand-alone HTML report)."""
    if not visuals:
        return
    pages = {}
    for label, path in (("before", original), ("after", mended)) if mended else (("before", original),):
        hidden = [is_hidden(s) for s in Deck(path).slides]
        page_of = {}
        page = 0
        for n, h in enumerate(hidden, 1):
            if not h:
                page += 1
                page_of[n] = page
        pages[label] = (renderer.to_pdf(path, label), page_of)
    # pdftoppm per page, four at a time (~35 ms each, one call per page keeps the file names). Each
    # (pdf, page) once: "before" and "after" can be the same PDF when nothing on the deck changed.
    from concurrent.futures import ThreadPoolExecutor
    wanted = {(pages[label][0], pages[label][1][v.slide]) for v in visuals for label in pages
              if v.slide in pages[label][1]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        images = dict(zip(wanted, pool.map(lambda key: renderer.page_image(*key), wanted)))
    for v in visuals:
        raw = {}
        for label, attr in (("before", "before_png"), ("after", "after_png")):
            if label not in pages:
                continue
            pdf, page_of = pages[label]
            if v.slide in page_of:
                raw[label] = images[(pdf, page_of[v.slide])]
                if image_dir:
                    name = f"slide-{v.slide}-{label}.jpg"
                    (image_dir / name).write_bytes(raw[label])
                    setattr(v, attr, name)
                else:
                    setattr(v, attr, "data:image/jpeg;base64," + base64.b64encode(raw[label]).decode())
        if len(raw) == 2:
            v.looks_same = _same_picture(raw["before"], raw["after"])
            v.diff_pct = 0.0 if v.looks_same else _diff_pct(raw["before"], raw["after"])


def _same_picture(a: bytes, b: bytes, noise: int = 40) -> bool:
    """True when two renders differ only by JPEG noise (font renames that don't change the look)."""
    import io
    from PIL import Image, ImageChops
    ia, ib = Image.open(io.BytesIO(a)).convert("L"), Image.open(io.BytesIO(b)).convert("L")
    if ia.size != ib.size:
        return False
    return ImageChops.difference(ia, ib).point(lambda v: 255 if v > noise else 0).getbbox() is None


def _diff_pct(a: bytes, b: bytes, noise: int = 40) -> float | None:
    """Percent of the slide's pixels that visibly changed (tuning: "did this change even show?")."""
    import io
    from PIL import Image, ImageChops
    ia, ib = Image.open(io.BytesIO(a)).convert("L"), Image.open(io.BytesIO(b)).convert("L")
    if ia.size != ib.size:
        return None
    hist = ImageChops.difference(ia, ib).point(lambda v: 255 if v > noise else 0).histogram()
    return round(100 * hist[255] / (ia.size[0] * ia.size[1]), 2)


GEOMETRY = {"left": "position", "top": "position", "width": "width", "height": "height"}


def _change_label(changes) -> str:
    """One readable line per property, first value → last value (a fix nudged in rounds would otherwise
    list every step, in EMU: CLARB 11 showed seven 'L009 width: 2948755 → 2919267' entries)."""
    from engine.core import EMU_PER_INCH
    first, last = {}, {}
    for c in changes:
        key = (c.check_id, c.prop)
        first.setdefault(key, c.before)
        last[key] = c.after
    out = []
    for (cid, prop), before in first.items():
        after = last[(cid, prop)]
        if prop in GEOMETRY and isinstance(before, int) and isinstance(after, int):
            name = {"left": "moved right" if after > before else "moved left",
                    "top": "moved down" if after > before else "moved up"}.get(prop, prop)
            out.append(f"{cid} {name}: {before / EMU_PER_INCH:.2f} → {after / EMU_PER_INCH:.2f} in")
        else:
            out.append(f"{cid} {prop}: {before} → {after}")
    return "; ".join(out)

