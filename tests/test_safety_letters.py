"""Review 2026-10-13 item 1.6: the safety pass judges by letters like L008/L010, and fit fixes leave boxes
PowerPoint is shrinking (autofit) alone. No PowerPoint: fake layouts."""
import pytest
from lxml import etree
from pptx.oxml.ns import qn

from engine.core import fit, runner
from engine.core.deck import Deck
from engine.core.edits import EditSession, FixRefused
from engine.core.layout.pdf import Line, ShapeText, Word
from tests.fixtures.builders import make_deck, text_box

IN = 914400


class FakeLayout:
    def __init__(self, deck, shapes, cut=None, apart=None):
        self.deck, self._shapes = deck, shapes
        if cut is not None:
            self.cut_off = lambda n, line, edge: cut
        if apart is not None:
            self.letters_apart = lambda n, a, b: apart

    def slide(self, n):
        return self._shapes


def _line(x, y, w, h, words=("Hello",)):
    return Line(x, y, x + w, y + h, list(words), [Word(words[0], x, x + w)])


def _deck(tmp_path, *boxes):
    return Deck(make_deck(tmp_path, *boxes))


def test_box_past_the_edge_with_clean_letters_is_not_off(tmp_path):
    deck = _deck(tmp_path, text_box("Hello", x=1, y=0.1))
    sid = deck.slide_shapes(1)[0].shape_id
    st = {sid: ShapeText(sid, [_line(IN, -0.2 * IN, 2 * IN, 0.6 * IN)])}
    ctx = runner.make_context(runner.RunConfig())
    assert runner._health(deck, FakeLayout(deck, st), 1, ctx).off == 1          # no picture: the box decides
    assert runner._health(deck, FakeLayout(deck, st, cut=False), 1, ctx).off == 0
    assert runner._health(deck, FakeLayout(deck, st, cut=True), 1, ctx).off == 1


def test_lines_the_picture_shows_apart_are_not_a_collision(tmp_path):
    deck = _deck(tmp_path, text_box("IL", x=1, y=1), text_box("331", x=1, y=1.3))
    a, b = (sv.shape_id for sv in deck.slide_shapes(1))
    st = {a: ShapeText(a, [_line(IN, IN, IN, 0.5 * IN, ("IL",))]),
          b: ShapeText(b, [_line(IN, 1.15 * IN, IN, 0.5 * IN, ("331",))])}
    ctx = runner.make_context(runner.RunConfig())
    assert runner._health(deck, FakeLayout(deck, st), 1, ctx).collisions == 1
    assert runner._health(deck, FakeLayout(deck, st, apart=True), 1, ctx).collisions == 0


def test_shrinking_autofit_box_rule_is_a_switch(tmp_path):
    deck = _deck(tmp_path, text_box("Hello there", x=1, y=1, w=4))
    sv = deck.slide_shapes(1)[0]
    body = sv.shape.text_frame._txBody.find(qn("a:bodyPr"))
    for child in list(body):
        body.remove(child)
    auto = etree.SubElement(body, qn("a:normAutofit"))
    edits = EditSession(deck)
    narrower = fit.Plan(left=sv.bounds.left, top=sv.bounds.top, width=sv.bounds.width - IN)
    assert not fit.autofit(sv)                      # autofit on but not shrinking: fixes still allowed
    auto.set("fontScale", "85000")
    assert fit.autofit(sv)
    from types import SimpleNamespace
    with pytest.raises(FixRefused, match="autofit"):       # only with the switch on (off by default)
        fit.apply(edits, sv, narrower, "test", ctx=SimpleNamespace(thresholds={"fit_skip_shrinking_autofit": True}))
    assert not edits.changes
    fit.apply(edits, sv, narrower, "test", ctx=SimpleNamespace(thresholds={}))
    assert edits.changes, "default: the fix is made"
