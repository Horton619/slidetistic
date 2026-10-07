"""scan → fix → write → re-scan → reconcile. One check failing never stops the run."""
from __future__ import annotations

from dataclasses import dataclass, field
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

    def summary(self) -> dict:
        problems = [f for f in self.findings if not f.informational]
        count = lambda s: sum(1 for f in problems if f.status == s)
        return {
            "type": "summary",
            "input": str(self.input_path),
            "output": str(self.output_path) if self.output_path else None,
            "green_fixed": count(Status.GREEN_FIXED),
            "yellow": count(Status.YELLOW),
            "red": count(Status.RED),
            "tool_error": count(Status.TOOL_ERROR),
            "informational": sum(1 for f in self.findings if f.informational),
            "clean_checks": self.clean_checks,
            "changes": len(self.changes),
        }


def make_context(config: RunConfig) -> Context:
    return Context(thresholds=rules.load("thresholds"), preset=config.preset,
                   crew_fonts={f.casefold() for f in config.crew_fonts})


def detect_all(deck: Deck, checks: list[type[Check]], config: RunConfig, ctx: Context,
               emit: Emit = _noop) -> tuple[list[Finding], list[str]]:
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
    before, _ = detect_all(Deck(path), checks, config, ctx, emit)

    # Fix in dependency order, re-detecting each check on the working deck so earlier
    # fixes (fonts) are reflected in later checks' findings (geometry, layout).
    deck = Deck(path)
    edits = EditSession(deck)
    outcome: dict[tuple, tuple[str, str]] = {}   # finding key → (kind, detail)
    errors: list[Finding] = []
    fixers = [c for c in checks if config.fix_on(c)]
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

    target = Path(out_path) if out_path else output_path_for(path)
    if target.resolve() == path.resolve():
        raise ValueError("Refusing to overwrite the input file")
    out = deck.save(target)
    emit({"type": "progress", "stage": "rescan"})
    after, clean = detect_all(Deck(out), checks, config, ctx)

    findings = _reconcile(before, after, outcome, edits.changes) + errors
    result = Result(input_path=path, findings=findings, clean_checks=clean,
                    changes=edits.changes, output_path=out)
    for c in edits.changes:
        emit({"type": "change", **c.to_dict()})
    for f in findings:
        emit({"type": "finding", **f.to_dict()})
    emit(result.summary())
    return result


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
            still.status = Status.RED
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
            culprit = touched_by.get((f.slide, f.shape_id))
            f.status = Status.RED
            f.evidence["introduced_by"] = culprit or "appeared after repair"
        out.append(f)
    return out
