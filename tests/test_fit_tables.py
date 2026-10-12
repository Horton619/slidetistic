"""Fit fixes on tables (PC suite 2026-10-11, Loop Lid slide 6): a table's text lives in its cells and its
frame width doesn't size the columns, so the only fit change allowed is moving the whole frame."""
from engine.core import Deck
from engine.core.fit import plan_fit
from engine.core.layout.pdf import Line, ShapeText, Word
from tests.fixtures.builders import make_deck, table

IN = 914400


def test_table_in_the_safe_border_is_only_ever_moved(tmp_path):
    deck = Deck(make_deck(tmp_path, table(rows=2, cols=2, text="cell", x=2, y=6.9, w=4, h=0.5)))
    sv = next(s for s in deck.slide_shapes(1) if s.text_bearing)
    assert not sv.shape.has_text_frame
    b = sv.bounds
    words = [Word("cell", b.left + 0.1 * IN, b.left + 0.6 * IN), Word("cell", b.left + 2.1 * IN, b.left + 2.6 * IN)]
    lines = [Line(b.left + 0.1 * IN, b.top + 0.05 * IN, b.left + 2.6 * IN, b.top + 0.3 * IN, ["cell", "cell"], words),
             Line(b.left + 0.1 * IN, b.top + 0.3 * IN, b.left + 2.6 * IN, b.top + 0.55 * IN, ["cell", "cell"], words)]
    st = ShapeText(sv.shape_id, lines, [0, 0])
    W, H = deck.slide_width, deck.slide_height
    safe = (0.05 * W, 0.05 * H, 0.95 * W, 0.95 * H)
    plan = plan_fit(deck, sv, st, {sv.shape_id: st}, safe, 12700, accept=lambda orphans, total: True,
                    fonts=(0.9,), spacings=(0.9,), move=True)     # only shrink options offered
    assert plan is not None
    assert (plan.font, plan.spacing) == (1.0, 1.0)
    assert plan.width == b.width and plan.top < b.top            # moved up, same size
