"""Review 2026-10-13 item 3.4: a repair never adds or removes slides or shapes, changes a word, or drops media."""
import zipfile

from engine.core import invariants
from tests.fixtures.builders import make_deck, text_box


def _rewrite(src, dst, member, fn):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for i in zin.infolist():
            data = zin.read(i)
            zout.writestr(i, fn(data) if i.filename == member else data)


def test_a_deck_keeps_its_promises_against_itself(tmp_path):
    deck = make_deck(tmp_path, text_box("Hello there"), text_box("Second box"))
    assert invariants.broken(deck, deck) == []


def test_changed_text_is_reported(tmp_path):
    deck = make_deck(tmp_path, text_box("Hello there"))
    out = tmp_path / "out.pptx"
    _rewrite(deck, out, "ppt/slides/slide1.xml", lambda d: d.replace(b"there", b"world"))
    [problem] = invariants.broken(deck, out)
    assert "text changed" in problem and "there" in problem and "world" in problem


def test_lost_shape_is_reported(tmp_path):
    deck = make_deck(tmp_path, text_box("Hello"), text_box("Bye"))
    out = tmp_path / "out.pptx"

    def drop_last_shape(d):
        i = d.rindex(b"<p:sp>")
        return d[:i] + d[d.index(b"</p:sp>", i) + len(b"</p:sp>"):]
    _rewrite(deck, out, "ppt/slides/slide1.xml", drop_last_shape)
    problems = invariants.broken(deck, out)
    assert any("shapes changed" in p for p in problems) and any("text changed" in p for p in problems)
