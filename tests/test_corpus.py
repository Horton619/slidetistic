"""Snapshot tests on real decks (`pytest -m corpus`). Client decks and snapshots never enter git.

Per deck: scan findings, plus (when there's something to fix) a repair into a temp folder and a
second repair of that output. Compared with the saved snapshot; a difference fails the test and is
summarised per check at the end. Accept a reviewed diff with `--update-snapshots`.

Always fails, snapshot or not: a check crashing, a repair introducing a problem, a second repair
changing anything.
"""
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path

import pytest

from engine.core import Status, registry
from engine.core.runner import RunConfig, repair, scan
from tests.conftest import REPO, corpus_root

pytestmark = pytest.mark.corpus
SNAPSHOTS = REPO / "corpus" / "snapshots"
CHECKS = registry.discover()
FIX_ON = {c.id for c in CHECKS if RunConfig().fix_on(c)}
DELTAS: Counter = Counter()          # (check, status, "+"/"-") across the corpus, for the summary
CHANGED_DECKS: list[str] = []


SKIP_DIRS = {"site-packages", "node_modules", "venv", ".venv", "myenv", "__MACOSX"}


SF_DATALESS = 0x40000000    # macOS: cloud placeholder (Dropbox/iCloud online-only); reading it downloads it


def find_decks(root: Path) -> list[Path]:
    """Real decks only: no Office lock files, our own outputs, software folders, or online-only files."""
    return sorted(p for p in root.rglob("*.pptx")
                  if p.is_file() and not getattr(p.stat(), "st_flags", 0) & SF_DATALESS and not p.name.startswith(("~$", "._")) and " - mended" not in p.name
                  and not SKIP_DIRS & set(p.relative_to(root).parts))


def pytest_generate_tests(metafunc):
    if "deck" not in metafunc.fixturenames:
        return
    root = corpus_root(metafunc.config)
    decks = find_decks(root) if root and root.is_dir() else []
    if not decks:
        metafunc.parametrize("deck", [pytest.param(None, marks=pytest.mark.skip(
            reason="no corpus: pass --corpus, set SLIDETISTIC_CORPUS, or write the folder into .corpus-path"))])
        return
    metafunc.parametrize("deck", decks, ids=[str(d.relative_to(root)) for d in decks])


def rows(findings) -> list[list]:
    """What's compared: check, status, place, subject. Message wording may change freely."""
    return sorted([f.check_id, f.status.value, f.slide or 0, f.shape_id or 0, f.subject] for f in findings)


def current(deck: Path, tmp_path: Path) -> dict:
    try:
        result = scan(deck, CHECKS, RunConfig())
    except zipfile.BadZipFile as e:
        pytest.skip(f"damaged deck: {e}")
    snap = {"checks": {c.id: c.version for c in CHECKS}, "scan": rows(result.findings), "repair": None}
    errors = [f for f in result.findings if f.status == Status.TOOL_ERROR]
    assert not errors, f"check crashed: {[(f.check_id, f.message) for f in errors]}"

    if any(f.check_id in FIX_ON and f.status in (Status.RED, Status.YELLOW) for f in result.findings):
        try:
            once = repair(deck, CHECKS, RunConfig(), out_path=tmp_path / "once.pptx")
            twice = repair(once.output_path, CHECKS, RunConfig(), out_path=tmp_path / "twice.pptx")
        finally:
            # Repaired copies of big decks add up to tens of GB over a corpus run: delete as we go.
            for name in ("once.pptx", "twice.pptx"):
                (tmp_path / name).unlink(missing_ok=True)
        introduced = [f for f in once.findings if "introduced_by" in f.evidence]
        assert not introduced, f"repair introduced problems: {[(f.check_id, f.subject, f.evidence['introduced_by']) for f in introduced]}"
        assert not twice.changes, f"second repair still changed {len(twice.changes)} things (fix not idempotent)"
        snap["repair"] = {"findings": rows(once.findings), "changes": len(once.changes)}
    return snap


def test_corpus_deck(deck, tmp_path, request):
    root = corpus_root(request.config)
    rel = str(deck.relative_to(root))
    path = SNAPSHOTS / (hashlib.sha1(rel.encode()).hexdigest()[:16] + ".json")
    now = {"deck": rel, **current(deck, tmp_path)}

    if request.config.getoption("--update-snapshots"):
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(now, indent=1))
        return
    if not path.exists():
        CHANGED_DECKS.append(f"{rel}  (new: no snapshot yet)")
        pytest.fail("no snapshot yet: review the findings, then run with --update-snapshots")

    before = json.loads(path.read_text())
    lines = _diff("scan", before["scan"], now["scan"]) + _diff(
        "after repair", (before["repair"] or {}).get("findings", []), (now["repair"] or {}).get("findings", []))
    if lines:
        CHANGED_DECKS.append(rel)
        pytest.fail(f"{rel}: results changed\n" + "\n".join(lines))


def _diff(label: str, old: list, new: list) -> list[str]:
    old_t, new_t = Counter(map(tuple, old)), Counter(map(tuple, new))
    out = []
    for sign, rows_ in (("-", old_t - new_t), ("+", new_t - old_t)):
        for row in sorted(rows_.elements()):
            if label == "scan":
                DELTAS[(row[0], row[1], sign)] += 1
            out.append(f"  {sign} [{label}] {row[0]} {row[1]:<10} slide {row[2] or '-':<4} {row[4]}")
    return out


def print_summary(tr):
    if not DELTAS and not CHANGED_DECKS:
        return
    tr.section("corpus diff")
    for (check, status, sign), n in sorted(DELTAS.items()):
        tr.write_line(f"  {check} {status:<10} {sign}{n}")
    tr.write_line(f"  decks changed: {len(CHANGED_DECKS)}")
    for d in CHANGED_DECKS:
        tr.write_line(f"    {d}")
