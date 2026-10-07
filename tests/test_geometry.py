import pytest

from engine.core import Deck
from engine.core.geometry import EMU_PER_INCH
from engine.core.shapes import GROUP, PICTURE, TABLE, TEXT_BOX
from tests.fixtures.builders import group, make_deck, picture, table, text_box


def test_group_children_get_absolute_bounds(tmp_path):
    # Child built at x=1; moving the group 2 in right must move the child's absolute x to 3.
    src = make_deck(tmp_path, group(text_box("child", x=1, w=2), x=3))
    shapes = Deck(src).iter_shapes()
    child = next(s for s in shapes if s.kind == TEXT_BOX)
    assert child.group_depth == 1
    assert child.bounds.left / EMU_PER_INCH == pytest.approx(3, abs=0.01)


def test_classify_and_text_bearing(tmp_path):
    src = make_deck(tmp_path, text_box("hi"), picture(), table(), group(text_box("g")))
    kinds = {(s.kind, s.text_bearing) for s in Deck(src).iter_shapes()}
    assert {(TEXT_BOX, True), (PICTURE, False), (TABLE, True), (GROUP, False)} <= kinds
