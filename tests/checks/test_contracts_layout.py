"""Layout checks with a fake layout (no PowerPoint): detection edge cases."""
from engine.core import Deck, registry
from engine.core.check import Context
from engine.core.layout.pdf import Line, ShapeText, Word
from engine.core.runner import RunConfig, make_context
from tests.fixtures.builders import make_deck, text_box

PT = 12700


def line(words, x, y, w_each=40, h=20):
    boxes, cur = [], x
    for t in words:
        boxes.append(Word(t, cur * PT, (cur + w_each) * PT))
        cur += w_each + 8
    return Line(x * PT, y * PT, (cur - 8) * PT, (y + h) * PT, list(words), boxes)


class FakeLayout:
    def __init__(self, by_slide):
        self.by_slide = by_slide

    def slide(self, n):
        return self.by_slide.get(n, {})

    def measure(self, n, sid):
        return self.slide(n).get(sid)


def detect(check_id, deck, layout):
    from dataclasses import replace
    cls = next(c for c in registry.discover() if c.id == check_id)
    return cls().detect(deck, replace(make_context(RunConfig()), layout=layout))


def test_l009_single_line_paragraph_is_never_an_orphan(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("Hello")))
    sid = deck.iter_shapes()[0].shape_id
    st = ShapeText(sid, [line(["Hello"], 200, 200)], [0])
    assert detect("L009", deck, FakeLayout({1: {sid: st}})) == []


def test_l009_short_titles_and_labels_are_not_orphans(tmp_path):
    # CLARB 11: "Board of / Directors", "Leadership Advisory Council / Chair" are designed breaks.
    deck = Deck(make_deck(tmp_path, text_box("Leadership Advisory Council Chair")))
    sid = deck.iter_shapes()[0].shape_id
    st = ShapeText(sid, [line(["Leadership", "Advisory", "Council"], 200, 200), line(["Chair"], 200, 230)], [0, 0])
    assert detect("L009", deck, FakeLayout({1: {sid: st}})) == []


def test_l009_flags_lonely_last_word_but_not_a_broken_doi(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("a b c d e whole. https://doi.org/10.1007/s00737-024- 01508-3")))
    sid = deck.iter_shapes()[0].shape_id
    st = ShapeText(sid, [line(["a", "b", "c", "d", "e"], 200, 200), line(["whole."], 200, 230),
                         line(["https://doi.org/10.1007/s00737-024-"], 200, 300), line(["01508-3"], 200, 330)],
                   [0, 0, 1, 1])
    found = detect("L009", deck, FakeLayout({1: {sid: st}}))
    assert [f.evidence["word"] for f in found] == ["whole."]
