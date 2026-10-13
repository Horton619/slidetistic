"""L008 after David's 2026-10-12 review (and 305 votes): header/footer text is placed on purpose, small text near
an edge is left as designed, and text sitting on a shape moves with the shape or not at all."""
import pytest
from pptx.enum.shapes import MSO_SHAPE

from engine.core import EMU_PER_INCH, Status
from engine.core.edits import EditSession, FixRefused
from engine.core.layout.pdf import ShapeText
from tests.fixtures.builders import text_box
from tests.test_fit import FakeLayout, _l008, setup, words_line

IN = EMU_PER_INCH


def rect(x, y, w, h, name="Panel"):
    def add(shapes):
        shp = shapes.add_shape(MSO_SHAPE.RECTANGLE, int(x * IN), int(y * IN), int(w * IN), int(h * IN))
        shp.name = name
        return shp
    return add


def _run(tmp_path, *shapes, lines):
    deck, sv = setup(tmp_path, *shapes)
    layout = FakeLayout({sv[name].shape_id: ShapeText(sv[name].shape_id, ls, list(range(len(ls))))
                         for name, ls in lines.items()})
    check, ctx = _l008(deck, layout)
    return deck, sv, check, ctx


def _fix(deck, check, ctx, finding):
    edits = EditSession(deck)
    edits.begin(type(check))
    check.fix(deck, finding, edits, ctx)
    return edits


def test_footer_text_in_the_border_is_not_flagged(tmp_path):
    # Bottom 15 % of a 7.5 in slide = below 6.375 in. The footer sits in the bottom border on purpose.
    deck, sv, check, ctx = _run(tmp_path, text_box("Footer", x=1, y=7.0, w=4, h=0.4, name="Foot"),
                                lines={"Foot": [words_line(["Footer"], 1.1, 7.05, h_in=0.3)]})
    assert [f for f in check.detect(deck, ctx) if f.shape_name == "Foot"] == []


def test_footer_text_off_the_slide_stays_red_and_is_not_moved(tmp_path):
    deck, sv, check, ctx = _run(tmp_path, text_box("Footer", x=1, y=7.0, w=4, h=0.4, name="Foot"),
                                lines={"Foot": [words_line(["Footer"], 1.1, 7.2, h_in=0.4)]})
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "Foot"]
    assert f.status == Status.RED
    with pytest.raises(FixRefused, match="header/footer"):
        _fix(deck, check, ctx, f)


def test_small_text_near_the_edge_is_left_as_designed(tmp_path):
    # Mid-slide label, 2×0.5 in (1 % of the slide), reaching into the left border: reported, not moved.
    deck, sv, check, ctx = _run(tmp_path, text_box("Label", x=0.2, y=3, w=2, h=0.5, name="Label"),
                                lines={"Label": [words_line(["Label"], 0.3, 3.05)]})
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "Label"]
    assert f.status == Status.YELLOW
    with pytest.raises(FixRefused, match="small text"):
        _fix(deck, check, ctx, f)


def test_a_big_block_near_the_edge_is_pulled_in(tmp_path):
    # 9×3.5 in body (31 % of a 13.33×7.5 slide) reaching into the left border: still fixed.
    deck, sv, check, ctx = _run(tmp_path, text_box("Body text", x=0.2, y=2, w=9, h=3.5, name="Body"),
                                lines={"Body": [words_line(["Body", "text"], 0.3, 2.1)]})
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "Body"]
    edits = _fix(deck, check, ctx, f)
    assert any(c.shape_name == "Body" for c in edits.changes)


def test_text_on_a_shape_moves_with_the_shape(tmp_path):
    # A caption on a coloured panel, running off the left edge: both move by the same amount.
    deck, sv, check, ctx = _run(tmp_path, rect(-0.3, 3, 3, 1, name="Panel"),
                                text_box("Caption", x=-0.2, y=3.1, w=2.6, h=0.8, name="Cap"),
                                lines={"Cap": [words_line(["Caption"], -0.1, 3.2)]})
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "Cap"]
    assert f.status == Status.RED
    edits = _fix(deck, check, ctx, f)
    moves = {c.shape_name: c.after - c.before for c in edits.changes if c.prop == "left"}
    assert set(moves) == {"Cap", "Panel"} and moves["Cap"] == pytest.approx(moves["Panel"], abs=2)
    assert edits.notes[-1]["features"]["fix"] == "pair" and edits.notes[-1]["features"]["on_shape"] is True


def test_text_on_a_shape_that_cant_move_with_it_is_left(tmp_path):
    # The panel is as wide as the slide's safe zone allows no room: moving both would push the panel off the right.
    deck, sv, check, ctx = _run(tmp_path, rect(0, 3, 13.3, 1, name="Strip"),
                                text_box("Caption", x=-0.2, y=3.1, w=2.6, h=0.8, name="Cap"),
                                lines={"Cap": [words_line(["Caption"], -0.1, 3.2)]})
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "Cap"]
    with pytest.raises(FixRefused, match="leave the slide"):
        _fix(deck, check, ctx, f)


def test_text_only_partly_over_a_shape_uses_the_normal_fix(tmp_path):
    # Look-alike: the text box overlaps the panel by under 80 %, so it isn't "on" it.
    deck, sv, check, ctx = _run(tmp_path, rect(-0.3, 3, 1, 1, name="Tab"),
                                text_box("Caption", x=-0.2, y=3.1, w=2.6, h=0.8, name="Cap"),
                                lines={"Cap": [words_line(["Caption"], -0.1, 3.2)]})
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "Cap"]
    edits = _fix(deck, check, ctx, f)
    assert {c.shape_name for c in edits.changes} == {"Cap"}


def test_small_text_near_the_edge_is_a_note_and_not_counted_as_yellow(tmp_path):
    from engine.core.runner import Result
    deck, sv, check, ctx = _run(tmp_path, text_box("Label", x=0.2, y=3, w=2, h=0.5, name="Label"),
                                text_box("Body text", x=0.2, y=2, w=9, h=3.5, name="Body"),
                                lines={"Label": [words_line(["Label"], 0.3, 6.0)],
                                       "Body": [words_line(["Body", "text"], 0.3, 2.1)]})
    found = {f.shape_name: f for f in check.detect(deck, ctx)}
    assert found["Label"].is_note and not found["Body"].is_note
    s = Result(input_path=tmp_path / "x.pptx", findings=list(found.values())).summary()
    assert (s["yellow"], s["notes"]) == (1, 1)


def test_a_slide_with_only_notes_is_in_the_notes_tier():
    from engine.visual import Box, SlideVisual
    v = SlideVisual(3, after_boxes=[Box(1, 1, 5, 5, "L008: …", "layout", "note")])
    assert v.tier == 5 and not v.needs_eyes
    v.after_boxes.append(Box(1, 1, 5, 5, "L011: …", "layout", "yellow"))
    assert v.tier == 3
