"""Tuning (David 2026-10-11): layout fixes are described in numbers, approved gates stop the fixes David's
votes say aren't worth making, and the review bundle carries the net change for each changed slide."""
from engine import visual
from engine.core import registry, tuning
from engine.core.runner import RunConfig, repair
from tests.fixtures.builders import make_deck, text_box
from tests.test_fit_settles import TEXTS, stand_in_powerpoint  # noqa: F401 — pytest fixture


def test_gate_conditions():
    f = {"check": "L008", "fix": "move", "move_in": 0.08, "role": "body", "severity": "yellow"}
    assert tuning.matches({"check": "L008", "when": {"move_in": {"max": 0.1}}}, f)
    assert not tuning.matches({"check": "L008", "when": {"move_in": {"min": 0.1}}}, f)
    assert tuning.matches({"fix": ["move", "push"], "when": {"role": ["body", "text"]}}, f)
    assert not tuning.matches({"check": ["L009"]}, f)
    assert not tuning.matches({"when": {"font_pt": {"max": 20}}}, f)       # missing feature never matches
    assert tuning.matches({"when": {"severity": "yellow"}}, f)


def _orphan_deck(tmp_path):
    return make_deck(tmp_path, text_box(TEXTS[0], x=1, y=2, w=3.86, h=2.5, name="Body"))


def test_layout_fixes_are_described_and_reach_the_review(tmp_path, stand_in_powerpoint):
    stand_in_powerpoint(0.0)
    src = _orphan_deck(tmp_path)
    result = repair(src, registry.discover(), RunConfig(layout=True), out_path=tmp_path / "out.pptx")
    assert any(c.check_id == "L009" for c in result.changes)
    note = next(n for n in result.notes if n["features"]["check"] == "L009")
    f = note["features"]
    assert f["fix"] in tuning.FIX_KINDS and f["orphan_words"] >= 1 and f["severity"] == "yellow"
    assert f["words"] > 10 and note["gate"] is None
    shown = next(v for v in visual.plan(result, src, result.output_path) if v.slide == 1)
    [t] = shown.tuning
    assert t["check"] == "L009" and t["shape_id"] == note["shape_id"] and t["attempts"] >= 1
    assert t["width_pct"] != 0 and shown.tuning_sig


def test_a_gate_leaves_the_box_untouched(tmp_path, stand_in_powerpoint, monkeypatch):
    stand_in_powerpoint(0.0)
    monkeypatch.setattr(tuning, "gates", lambda: [{"id": "T900", "check": "L009", "action": "skip",
                                                   "why": "test gate"}])
    src = _orphan_deck(tmp_path)
    result = repair(src, registry.discover(), RunConfig(layout=True), out_path=tmp_path / "out.pptx")
    assert not [c for c in result.changes if c.check_id.startswith("L")]
    assert result.notes and all(n["gate"] == "T900" for n in result.notes)
    orphan = next(f for f in result.findings if f.check_id == "L009")
    assert orphan.status.value == "yellow" and "T900" in orphan.evidence["fix_result"]
