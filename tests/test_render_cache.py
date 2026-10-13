"""Review 2026-10-13 items 3.2/3.3: PowerPoint's PDFs reused between runs, and replayed in tests. No PowerPoint."""
import pytest

from engine import render, render_cache
from tests.fixtures.builders import make_deck, text_box


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SLIDETISTIC_RENDER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(render_cache, "MODE", "on")
    monkeypatch.setattr(render, "LOCK_FILE", tmp_path / "render.lock")
    monkeypatch.setattr(render_cache, "fonts_fingerprint", lambda: "fonts-a")
    return tmp_path


class Counting(render._Renderer):
    name = "counting"

    def __init__(self, work):
        self.work, self.exports = work, 0

    def _export(self, pptx, label):
        self.exports += 1
        out = self.work / f"{label}-{self.exports}.pdf"
        out.write_bytes(b"%PDF-1.4 fake " + pptx.read_bytes()[:20])
        return out


def test_a_second_run_reuses_the_pdf(cache):
    deck = make_deck(cache, text_box("Hello"))
    first = Counting(cache)
    first.to_pdf(deck, "a")
    again = Counting(cache)           # a new process: nothing in memory
    pdf = again.to_pdf(deck, "a")
    assert first.exports == 1 and again.exports == 0 and pdf.exists()


def test_new_fonts_mean_a_new_render(cache, monkeypatch):
    deck = make_deck(cache, text_box("Hello"))
    Counting(cache).to_pdf(deck, "a")
    monkeypatch.setattr(render_cache, "fonts_fingerprint", lambda: "fonts-b")     # Get fonts installed one
    r = Counting(cache)
    r.to_pdf(deck, "a")
    assert r.exports == 1


def test_off_means_off(cache, monkeypatch):
    monkeypatch.setattr(render_cache, "MODE", "off")
    deck = make_deck(cache, text_box("Hello"))
    Counting(cache).to_pdf(deck, "a")
    r = Counting(cache)
    r.to_pdf(deck, "a")
    assert r.exports == 1


def test_replay_serves_recorded_pdfs_and_says_when_one_is_missing(cache, monkeypatch):
    rec = cache / "recorded"
    monkeypatch.setenv("SLIDETISTIC_RENDER_RECORD", str(rec))
    monkeypatch.setattr(render_cache, "MODE", "off")
    deck = make_deck(cache, text_box("Hello"))
    Counting(cache).to_pdf(deck, "a")
    replay = render_cache.ReplayRenderer(rec)
    assert replay.to_pdf(deck, "a").read_bytes().startswith(b"%PDF")
    (cache / "o").mkdir()
    other = make_deck(cache / "o", text_box("Something else"))
    with pytest.raises(render.RenderError, match="no recorded render"):
        replay.to_pdf(other, "a")
