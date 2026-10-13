"""Line boxes aren't letters (David 2026-10-12): a box holds the font's whole ascent and descent. Collisions
and 'off the slide' are judged by where letters are: the letter zone geometrically, and the rendered picture."""
from PIL import Image, ImageDraw

from engine.core import EMU_PER_INCH, Deck, fit
from engine.core.layout.pdf import Line, PdfLayout
from tests.fixtures.builders import make_deck, text_box

IN = EMU_PER_INCH


def line(top_in, h_in, left_in=1.0, right_in=2.0):
    return Line(left_in * IN, top_in * IN, right_in * IN, (top_in + h_in) * IN, ["x"], [])


def test_stacked_labels_boxes_overlap_but_letters_dont():
    # 'IL' over '331' on a map: boxes overlap by 35 % of a line, the letters don't meet.
    il, n331 = line(2.0, 0.30), line(2.0 + 0.30 * 0.65, 0.30)
    assert not fit.lines_collide(il, n331, 2 * 12700)


def test_lines_drawn_on_top_of_each_other_collide():
    assert fit.lines_collide(line(2.0, 0.30), line(2.08, 0.30), 2 * 12700)


class PictureLayout(PdfLayout):
    """A layout whose 'render' is a picture we draw: 120 px per inch."""
    def __init__(self, deck, img):
        super().__init__(deck, renderer=None)
        self._pages, self._page_of, self._gray = {1: []}, {1: 1}, {1: img}


def letters(img, x0, y0, x1, y1):
    """Letter-like strokes (about 30 % ink), not a solid block."""
    d = ImageDraw.Draw(img)
    for x in range(x0, x1, 7):
        d.rectangle([x, y0, x + 1, y1], fill=0)


def _canvas(deck):
    w, h = int(deck.slide_width / IN * 120), int(deck.slide_height / IN * 120)
    return Image.new("L", (w, h), 255)


def test_picture_shows_a_gap_between_stacked_lines(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("x")))
    img = _canvas(deck)
    letters(img, 120, 240, 240, 262)                   # upper line's letters: y 2.00–2.18 in
    letters(img, 120, 268, 240, 290)                   # lower line's letters: y 2.23–2.42 in (a 6 px gap)
    lay = PictureLayout(deck, img)
    assert lay.letters_apart(1, line(1.95, 0.30), line(2.15, 0.30)) is True
    letters(img, 123, 258, 240, 272)                   # now the letters run into each other
    assert lay.letters_apart(1, line(1.95, 0.30), line(2.15, 0.30)) is False


def test_box_past_the_top_edge_is_not_cut_off_unless_letters_touch_it(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("x")))
    img = _canvas(deck)
    letters(img, 120, 30, 400, 90)                                  # letters well inside the slide
    lay = PictureLayout(deck, img)
    title = line(-0.26, 1.2, 1.0, 3.3)                              # its box starts 0.26 in above the slide
    assert lay.cut_off(1, title, "top") is False
    letters(img, 120, 0, 400, 10)                                   # letters run into the top edge
    assert lay.cut_off(1, title, "top") is True


def test_without_a_picture_the_geometry_rule_stands(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("x")))
    lay = PdfLayout(deck, renderer=None)
    lay._pages, lay._page_of = {1: []}, {}
    assert lay.letters_apart(1, line(2.0, 0.3), line(2.1, 0.3)) is None


def test_text_drawn_over_text_is_not_apart_despite_blank_rows_inside_the_lines(tmp_path):
    # Both lines' letters in the same band; the only blank rows are above the capitals and below the
    # baseline, inside the lines themselves. That's a collision.
    deck = Deck(make_deck(tmp_path, text_box("x")))
    img = _canvas(deck)
    letters(img, 120, 250, 240, 272)
    letters(img, 124, 252, 240, 274)
    lay = PictureLayout(deck, img)
    assert lay.letters_apart(1, line(2.0, 0.30), line(2.02, 0.30)) is False


def test_two_boxes_sharing_a_line_dont_collide_when_their_words_interleave():
    # Canva/Google exports split one line across text boxes: "First 10 | Elementary | School Hub".
    from engine.core.layout.pdf import Word
    a = Line(1 * IN, 2 * IN, 6 * IN, 2.4 * IN, ["First", "10", "School", "Hub"],
             [Word("First", 1.0 * IN, 1.6 * IN), Word("10", 1.7 * IN, 2.0 * IN),
              Word("School", 4.2 * IN, 5.0 * IN), Word("Hub", 5.1 * IN, 6.0 * IN)])
    b = Line(2.1 * IN, 2 * IN, 4.1 * IN, 2.4 * IN, ["Elementary"], [Word("Elementary", 2.1 * IN, 4.1 * IN)])
    assert not fit.lines_collide(a, b, 2 * 12700)
    b2 = Line(1.4 * IN, 2 * IN, 3.4 * IN, 2.4 * IN, ["Elementary"], [Word("Elementary", 1.4 * IN, 3.4 * IN)])
    assert fit.lines_collide(a, b2, 2 * 12700)          # now 'Elementary' sits on top of 'First 10'
