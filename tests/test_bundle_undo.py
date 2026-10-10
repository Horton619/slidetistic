"""Review bundle + undo-slide, without PowerPoint (no images, no layout)."""
import json

from engine import cli
from engine.core import Deck, EMU_PER_INCH
from tests.fixtures.builders import make_deck, text_box


def test_repair_writes_review_bundle_and_prefit(tmp_path):
    src = make_deck(tmp_path, text_box("Body", x=-0.56, name="Off"), text_box("x", font="Calibri (MS) Bold"))
    rd = tmp_path / "review"
    assert cli.main(["repair", str(src), "--out", str(tmp_path / "out.pptx"), "--review-dir", str(rd),
                     "--no-report", "--no-visual"]) == 0
    data = json.loads((rd / "review.json").read_text(encoding="utf-8"))
    assert data["summary"]["green_fixed"] >= 2 and data["prefit"] and (rd / "prefit.pptx").exists()
    assert {"findings", "changes", "visuals", "inventory", "downloads", "checks", "kinds"} <= set(data)


def test_undo_slide_restores_the_pre_layout_slide_only(tmp_path):
    prefit = make_deck(tmp_path, slides=[[text_box("A", x=1, name="A")], [text_box("B", x=1, name="B")]], name="prefit.pptx")
    mended = make_deck(tmp_path, slides=[[text_box("A", x=3, name="A")], [text_box("B", x=3, name="B")]], name="out.pptx")
    assert cli.main(["undo-slide", str(mended), "--prefit", str(prefit), "--slide", "2"]) == 0
    lefts = [round(sv.bounds.left / EMU_PER_INCH) for sv in Deck(mended).iter_shapes()]
    assert lefts == [3, 1]          # slide 1 keeps its fix, slide 2 is back to the pre-layout copy


def test_undo_slide_refuses_mismatched_decks(tmp_path, capsys):
    prefit = make_deck(tmp_path, text_box("A"), name="prefit.pptx")
    mended = make_deck(tmp_path, slides=[[text_box("A")], [text_box("B")]], name="out.pptx")
    assert cli.main(["undo-slide", str(mended), "--prefit", str(prefit), "--slide", "2", "--json"]) == 2


def test_set_overrides_a_threshold_for_one_run(tmp_path):
    from engine.core.runner import RunConfig, make_context
    ctx = make_context(RunConfig(overrides={"safe_zone_pct": 7}))
    assert ctx.thresholds["safe_zone_pct"] == 7 and cli._overrides(["safe_zone_pct=7", "x=1.5"]) == {"safe_zone_pct": 7, "x": 1.5}
