"""G001/G002 judged by the words PowerPoint drew, not the box (David 2026-10-10: box overhangs were mostly
false alarms). PowerPoint's PDF leaves out words outside the slide (broken_mac slides 18 and 20), so a word
missing from the render means it's off the slide."""
from pptx.enum.text import PP_ALIGN

from engine.core import Deck
from engine.core.layout.pdf import ShapeText
from tests.checks.helpers import Status
from tests.checks.test_contracts_layout import FakeLayout, detect, line
from tests.checks.test_G001_G004_geometry import aligned
from tests.fixtures.builders import make_deck, text_box

# 13.333 x 7.5 in slide = 960 x 540 pt


def one_box(tmp_path, box):
    deck = Deck(make_deck(tmp_path, box))
    return deck, deck.iter_shapes()[0].shape_id


def test_g001_overhanging_box_with_all_words_on_the_slide_is_silent(tmp_path):
    # broken_mac slide 19: centered box 9-15 in, words drawn 10.75-13.25 in.
    deck, sid = one_box(tmp_path, aligned(text_box("Centered words", x=9, w=6), PP_ALIGN.CENTER))
    drawn = ShapeText(sid, [line(["Centered", "words"], 780, 220)], [0])
    assert detect("G001", deck, None)[0].status == Status.YELLOW          # no render: still a maybe
    assert detect("G001", deck, FakeLayout({1: {sid: drawn}})) == []


def test_g001_words_missing_from_the_render_are_red(tmp_path):
    # broken_mac slide 18: box half off the left edge, 0 of 11 words drawn.
    deck, sid = one_box(tmp_path, aligned(text_box("Centered words here", x=-4, w=6), PP_ALIGN.CENTER))
    drawn = ShapeText(sid, [line(["here"], 20, 220)], [0])
    [f] = detect("G001", deck, FakeLayout({1: {sid: drawn}}))
    assert f.status == Status.RED and f.evidence["words_drawn"] == 1 and f.evidence["words_total"] == 3
    assert "2 of 3 words are off the left edge" in f.message


def test_g001_text_drawn_past_the_edge_is_red(tmp_path):
    deck, sid = one_box(tmp_path, aligned(text_box("Two words", x=9, w=6), PP_ALIGN.CENTER))
    drawn = ShapeText(sid, [line(["Two", "words"], 930, 220)], [0])         # ends at 1018 pt > 960
    [f] = detect("G001", deck, FakeLayout({1: {sid: drawn}}))
    assert f.status == Status.RED and "drawn past the right edge" in f.message


def test_g002_tall_box_with_every_word_visible_is_silent(tmp_path):
    deck, sid = one_box(tmp_path, text_box("Short caption", y=6.5, h=3))
    drawn = ShapeText(sid, [line(["Short", "caption"], 100, 470)], [0])
    assert detect("G002", deck, None)[0].status == Status.YELLOW
    assert detect("G002", deck, FakeLayout({1: {sid: drawn}})) == []


def test_g002_lines_cut_off_at_the_bottom_are_red(tmp_path):
    # broken_mac slide 20: 9 of 15 words drawn, the rest fell below the slide.
    deck, sid = one_box(tmp_path, text_box("Line one\nLine two\nLine three", y=6.2, h=3))
    drawn = ShapeText(sid, [line(["Line", "one"], 100, 450), line(["Line", "two"], 100, 480)], [0, 1])
    [f] = detect("G002", deck, FakeLayout({1: {sid: drawn}}))
    assert f.status == Status.RED and f.subject == "off-slide" and "2 of 6 words" in f.message


def test_hidden_slide_is_not_judged_from_a_render_it_isnt_in(tmp_path):
    deck, sid = one_box(tmp_path, aligned(text_box("Centered words", x=9, w=6), PP_ALIGN.CENTER))
    deck.slides[0]._element.set("show", "0")
    assert detect("G001", deck, FakeLayout({}))[0].status == Status.YELLOW
