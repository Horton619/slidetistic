"""Fit engine with a fake layout (no PowerPoint): prediction, search, collision safety."""
from dataclasses import replace

from engine.core import Deck, EMU_PER_INCH, fit, registry
from engine.core.edits import EditSession
from engine.core.layout.pdf import Line, ShapeText, Word
from engine.core.runner import RunConfig, make_context
from tests.fixtures.builders import make_deck, text_box

PT = 12700
IN = EMU_PER_INCH


def words_line(texts, x_in, y_in, word_in=0.8, gap_in=0.1, h_in=0.4):
    boxes, cur = [], x_in
    for t in texts:
        boxes.append(Word(t, cur * IN, (cur + word_in) * IN))
        cur += word_in + gap_in
    return Line(x_in * IN, y_in * IN, (cur - gap_in) * IN, (y_in + h_in) * IN, list(texts), boxes)


class FakeLayout:
    def __init__(self, slide):
        self.s = slide

    def slide(self, n):
        return self.s

    def measure(self, n, sid):
        return self.s.get(sid)


def setup(tmp_path, *shapes):
    deck = Deck(make_deck(tmp_path, *shapes))
    return deck, {sv.name: sv for sv in deck.iter_shapes()}


def test_reflow_reproduces_the_breaks_it_was_calibrated_on(tmp_path):
    # Box 4.6 in wide (0.1 in margins → 4.4 in text): 5 words of 0.8 in + 0.1 gaps fit per line.
    deck, sv = setup(tmp_path, text_box("a b c d e f g h i j k", x=1, y=1, w=4.6, h=2, name="B"))
    lines = [words_line("a b c d e".split(), 1.1, 1.0), words_line("f g h i j".split(), 1.1, 1.5),
             words_line(["k"], 1.1, 2.0)]
    st = ShapeText(sv["B"].shape_id, lines, [0, 0, 0])
    _, orphans, total = fit.Reflow(sv["B"], st).predict(sv["B"].bounds.left, sv["B"].bounds.width)
    assert (orphans, total) == (1, 3)


def test_search_narrows_to_give_the_orphan_company(tmp_path):
    deck, sv = setup(tmp_path, text_box("a b c d e f g h i j k", x=1, y=1, w=4.6, h=2, name="B"))
    st = ShapeText(sv["B"].shape_id, [words_line("a b c d e".split(), 1.1, 1.0),
                                      words_line("f g h i j".split(), 1.1, 1.5), words_line(["k"], 1.1, 2.0)], [0, 0, 0])
    safe = fit.safe_rect(deck, 5)
    plan = fit.plan_fit(deck, sv["B"], st, {sv["B"].shape_id: st}, safe, 2 * PT, narrow_pct=15, widen_pct=10,
                        accept=lambda o, t: o == 0 and t <= 3)
    assert plan and plan.width < sv["B"].bounds.width     # 4 words per line → 4/4/3, no orphan


def test_search_rejects_widths_that_hit_other_text(tmp_path):
    deck, sv = setup(tmp_path, text_box("a b c d e f g h i j k", x=1, y=1, w=4.6, h=2, name="B"),
                     text_box("neighbour", x=5.75, y=1, w=2, h=0.5, name="N"))
    st = ShapeText(sv["B"].shape_id, [words_line("a b c d e".split(), 1.1, 1.0),
                                      words_line("f g h i j".split(), 1.1, 1.5), words_line(["k"], 1.1, 2.0)], [0, 0, 0])
    other = ShapeText(sv["N"].shape_id, [words_line(["neighbour"], 5.75, 1.0)], [0])
    layout = {sv["B"].shape_id: st, sv["N"].shape_id: other}
    plan = fit.plan_fit(deck, sv["B"], st, layout, fit.safe_rect(deck, 5), 2 * PT, narrow_pct=0, widen_pct=10,
                        accept=lambda o, t: t <= 2)              # only widening could reach 2 lines…
    assert plan is None                                         # …but that line would run into N


def test_plan_never_slides_text_onto_a_picture(tmp_path):
    # PAT 18: an orphan fix shoved a bullet block under an illustration and hid whole words.
    from tests.fixtures.builders import picture
    deck, sv = setup(tmp_path, text_box("a b c d e f g h i j k", x=1, y=1, w=4.6, h=2, name="B"),
                     picture(x=5.75, y=0.9, w=2, h=2))
    st = ShapeText(sv["B"].shape_id, [words_line("a b c d e".split(), 1.1, 1.0),
                                      words_line("f g h i j".split(), 1.1, 1.5), words_line(["k"], 1.1, 2.0)], [0, 0, 0])
    boxes = fit.obstacles(deck, 1, sv["B"].shape_id, st.lines)
    plan = fit.plan_fit(deck, sv["B"], st, {sv["B"].shape_id: st}, fit.safe_rect(deck, 5), 2 * PT, narrow_pct=0,
                        widen_pct=10, accept=lambda o, t: t <= 2, obstacle_boxes=boxes)
    assert boxes and plan is None


def test_plan_never_predicts_text_off_the_slide(tmp_path):
    # PAT 17: narrowing a tall block added lines and pushed the last one off the bottom.
    deck, sv = setup(tmp_path, text_box("x", x=1, y=5.5, w=4.6, h=1.8, name="B"))
    lines = [words_line("a b c d e".split(), 1.1, 5.6 + 0.5 * k) for k in range(3)]
    st = ShapeText(sv["B"].shape_id, lines, [0, 1, 2])
    plan = fit.plan_fit(deck, sv["B"], st, {sv["B"].shape_id: st}, fit.safe_rect(deck, 5), 2 * PT,
                        narrow_pct=15, accept=lambda o, t: True)
    assert plan is None or max(l.bottom for l in plan.lines) <= deck.slide_height


def _l008(deck, layout):
    cls = next(c for c in registry.discover() if c.id == "L008")
    ctx = replace(make_context(RunConfig()), layout=layout)
    return cls(), ctx


def test_l008_pushes_the_text_below_when_it_has_room(tmp_path):
    # A big title block in the top border (taller than the header band, so not a header strip: David
    # 2026-10-12); moving it down hits the body, which has room to move down first.
    deck, sv = setup(tmp_path, text_box("Title", x=1, y=0.05, w=8, h=3.4, name="T"),
                     text_box("Body", x=1, y=1.6, w=8, h=0.6, name="Body"))
    t = ShapeText(sv["T"].shape_id, [words_line(["Title"], 4, y, h_in=0.5) for y in (0.05, 0.55, 1.05)], [0, 1, 2])
    b = ShapeText(sv["Body"].shape_id, [words_line(["Body"], 4, 1.55, h_in=0.5)], [0])
    layout = FakeLayout({sv["T"].shape_id: t, sv["Body"].shape_id: b})
    check, ctx = _l008(deck, layout)
    [f] = [f for f in check.detect(deck, ctx) if f.shape_name == "T"]
    edits = EditSession(deck)
    edits.begin(type(check))
    check.fix(deck, f, edits, ctx)
    assert [c.shape_name for c in edits.changes] == ["Body"] and edits.changes[0].prop == "top"


def test_image_filled_shapes_count_as_graphics_and_panels_block_moves(tmp_path):
    # PAT 5: Canva's chart and map are freeform shapes FILLED WITH AN IMAGE, not pictures. Plain coloured
    # panels aren't graphics for detection (counting them flagged 45 harmless overlaps), but a fix must not
    # move text onto one it isn't on now (David 2026-10-12: "hit other elements").
    from lxml import etree
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
    from tests.fixtures.builders import picture

    def image_filled(shapes):
        pic = picture(x=9, y=6, w=0.5, h=0.5)(shapes)            # gives the slide an image relationship
        r_id = pic._element.blip_rId
        shp = shapes.add_shape(MSO_SHAPE.RECTANGLE, int(5.75 * IN), int(0.9 * IN), 2 * IN, 2 * IN)
        sp_pr = shp._element.find(qn("p:spPr"))
        fill = etree.fromstring(
            '<a:blipFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<a:blip r:embed="{r_id}"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>')
        sp_pr.find(qn("a:prstGeom")).addnext(fill)
        return shp

    def panel(shapes):
        return shapes.add_shape(MSO_SHAPE.RECTANGLE, int(1 * IN), int(3.5 * IN), 4 * IN, 2 * IN)

    deck, sv = setup(tmp_path, text_box("a b c", x=1, y=1, w=4.6, h=2, name="B"), image_filled, panel)
    st = ShapeText(sv["B"].shape_id, [words_line("a b c".split(), 1.1, 1.0)], [0])
    found = fit.obstacles(deck, 1, sv["B"].shape_id, st.lines)
    assert len(found) == 3          # the small picture, the image-filled freeform, and the panel
    assert [fit.is_graphic(s) for s in deck.slide_shapes(1)].count(True) == 2   # detection: not the panel
