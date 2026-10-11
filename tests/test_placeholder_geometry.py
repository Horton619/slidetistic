"""Moving a placeholder that takes its position from the layout (app run 2026-10-11: on the lower-thirds deck
the safe-zone fix moved such boxes sideways, python-pptx wrote only that value, and the boxes became
zero-size, so every slide's text vanished)."""
import pytest

from engine.core import EMU_PER_INCH, Deck
from engine.core.edits import EditSession, _inherits_xfrm
from tests.fixtures.builders import make_deck


def test_moving_an_inheriting_placeholder_keeps_its_size_and_top(tmp_path):
    deck = Deck(make_deck(tmp_path, layout=1, titles=["Aileen Caceres, MD, MPH, FACOG"]))
    sv = next(s for s in deck.slide_shapes(1) if s.shape.is_placeholder and s.text_bearing)
    assert _inherits_xfrm(sv.shape)
    top, width, height = sv.shape.top, sv.shape.width, sv.shape.height
    edits = EditSession(deck)
    edits.begin(type("Fix", (), {"id": "L008", "runs_after": []}))
    edits.set_geometry(sv, left=sv.shape.left + EMU_PER_INCH // 2)
    moved = next(s for s in deck.slide_shapes(1) if s.shape_id == sv.shape_id)
    assert (moved.shape.top, moved.shape.width, moved.shape.height) == (top, width, height)
    assert [c.prop for c in edits.changes] == ["left"]              # the pin itself isn't a reported change


@pytest.mark.powerpoint
def test_lower_thirds_repair_keeps_every_word_on_the_slide(tmp_path):
    """The real deck, rendered by PowerPoint: after repair no slide may lose words (needs the suite in Dropbox)."""
    from pathlib import Path
    from engine.core import registry
    from engine.core.runner import RunConfig, repair
    src = Path.home() / "Dropbox/SlideTistic Test Suite/AACS 26 RECORDS/PICTURES SLIDES ETC/CONCURRENT 1 LOWER THIRDS.pptx"
    if not src.exists():
        pytest.skip("suite deck not available")
    result = repair(src, registry.discover(), RunConfig(layout=True), out_path=tmp_path / "out.pptx")
    assert not [f for f in result.findings if f.check_id == "G001" and f.status.value == "red" and f.evidence.get("words_drawn") == 0]
