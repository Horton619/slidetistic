"""Which fonts shown text actually uses (David 2026-10-12): a font only named in an empty run, a master or a
layout isn't drawn, and F007 makes it a quiet note instead of a red."""
from lxml import etree
from pptx.oxml.ns import qn

from engine.core import Deck, registry
from engine.core.font_use import visible_fonts
from engine.core.runner import RunConfig, make_context
from tests.fixtures.builders import make_deck, text_box


def empty_run_font(font):
    """A text box whose only use of `font` is the end-of-paragraph marker (no text drawn with it)."""
    def add(shapes):
        tb = text_box("Shown text")(shapes)
        p = tb.text_frame.paragraphs[0]._p
        end = etree.SubElement(p, qn("a:endParaRPr"))
        etree.SubElement(end, qn("a:latin"), typeface=font)
        return tb
    return add


def _f007(deck):
    check = next(c for c in registry.discover() if c.id == "F007")()
    return {f.subject: f for f in check.detect(deck, make_context(RunConfig()))}


def test_explicit_fonts_on_shown_text_are_drawn(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("Hi", font="Gotham"), text_box("  ", font="Rockwell")))
    seen = visible_fonts(deck)
    assert seen["gotham"]["slides"] == [1]
    assert "rockwell" not in seen            # whitespace only: nothing drawn


def test_text_without_a_font_uses_the_theme_font(tmp_path):
    deck = Deck(make_deck(tmp_path, text_box("Hi")))
    assert "calibri" in visible_fonts(deck)   # python-pptx's default theme: Calibri


def test_a_missing_font_no_text_uses_is_a_note_not_a_red(tmp_path):
    deck = Deck(make_deck(tmp_path, empty_run_font("Gotham"), text_box("Hi", font="Proxima Nova")))
    found = _f007(deck)
    assert found["Gotham"].is_note and found["Gotham"].evidence["drawn"] is False
    assert found["Proxima Nova"].status.value == "red"
