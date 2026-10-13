"""Review 2026-10-13 item 3.3: a layout repair replayed from real Mac PowerPoint renders, so the fit loop is tested
without PowerPoint (CI). Recorded 2026-10-13 (PowerPoint 16.113.4) with:

    SLIDETISTIC_RENDER_CACHE=off SLIDETISTIC_RENDER_RECORD=tests/fixtures/renders/mac-layout-repair \
        venv/bin/python -m engine.cli repair <deck from _deck()> --layout --no-visual --out /tmp/out.pptx

If a change to the fixes makes the engine ask for a render that wasn't recorded, the test says so: record again
with real PowerPoint and check the new result is right before replacing the PDFs."""
from pathlib import Path

import pytest

from engine import render, render_cache
from engine.core import registry, runner
from tests.fixtures.builders import make_deck, text_box

RENDERS = Path(__file__).parent / "fixtures" / "renders" / "mac-layout-repair"


def _deck(folder: Path) -> Path:
    return make_deck(folder, slides=[
        [text_box("Quarterly results and the plan for next year", x=0.6, y=0.5, w=6.1, h=0.8, size=36)],
        [text_box("Text that starts a little past the right edge", x=9.8, y=3, w=3.9, h=1, size=20)],
        [text_box("Our members grew in every region this past year again", x=1, y=2, w=4.1, h=1.5, size=24)],
    ])


@pytest.mark.skipif(render._poppler_missing(), reason="needs Poppler (pdftotext, pdftoppm)")
def test_layout_repair_replayed_from_recorded_powerpoint_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDETISTIC_RENDER_REPLAY", str(RENDERS))
    monkeypatch.setattr(render, "PowerPointRenderer", lambda: render_cache.ReplayRenderer(RENDERS))
    monkeypatch.setattr(render.PowerPointRenderer, "available", staticmethod(lambda: (True, "")), raising=False)
    monkeypatch.setattr(runner, "_RENDERER", None)
    src = _deck(tmp_path)
    try:
        result = runner.repair(src, registry.discover(), runner.RunConfig(layout=True), out_path=tmp_path / "out.pptx")
    finally:
        runner.cleanup()
    moves = [(c.check_id, c.slide, c.prop, c.after) for c in result.changes if c.check_id.startswith("L")]
    assert moves == [("L008", 2, "left", 8324205)], "the off-slide box on slide 2 moves back in, nothing else moves"
    fixed = {(f.check_id, f.slide) for f in result.findings if f.status.value == "green_fixed"}
    assert {("G001", 2), ("L008", 2)} <= fixed
    assert not [f for f in result.findings if f.status.value == "tool_error"]
