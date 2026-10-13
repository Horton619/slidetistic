"""Review 2026-10-13 item 3.10: fit rounds 2+ can export only the slides the last round changed (opt-in).
Verified with real PowerPoint on CLARB 01-02 MASTER (2026-10-13): check mode found no difference in 5 rounds;
on = 49.7 s, off = 71.5 s. Here: the gates, the merge, check mode and the hint, without PowerPoint."""
import zipfile
from types import SimpleNamespace

from lxml import etree

from engine.core import runner
from engine.core.deck import Deck
from engine.core.layout.pdf import Line, PdfLayout
from engine.core.partial import write_subset
from tests.fixtures.builders import make_deck, text_box

CTX = SimpleNamespace(thresholds={"partial_export_min_export_s": 20, "partial_export_max_changed_pct": 25,
                                  "partial_export_hint_min_saving_s": 30, "partial_export_overhead_s": 3})


def _line(word, top=0):
    return Line(0, top, 100, top + 10, [word])


def test_subset_lists_only_the_kept_slides(tmp_path):
    deck = make_deck(tmp_path, slides=[[text_box(f"s{i}")] for i in range(1, 5)])
    out = tmp_path / "sub.pptx"
    assert write_subset(deck, out, {2, 4}) == [2, 4]
    root = etree.fromstring(zipfile.ZipFile(out).read("ppt/presentation.xml"))
    assert len(root.find("{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst")) == 2
    assert len(Deck(out).slides) == 2


def test_gates(tmp_path):
    first = SimpleNamespace(export_s=25.0, base=None)
    on = SimpleNamespace(partial_export="on")
    assert runner._partial_ok(on, CTX, {3}, first, 40)
    assert not runner._partial_ok(SimpleNamespace(partial_export="off"), CTX, {3}, first, 40)
    assert not runner._partial_ok(on, CTX, None, first, 40), "round 1 always draws everything"
    assert not runner._partial_ok(on, CTX, set(range(1, 12)), first, 40), "over 25% changed"
    assert not runner._partial_ok(on, CTX, {3}, SimpleNamespace(export_s=8.0, base=None), 40), "fast deck"
    later = SimpleNamespace(export_s=2.0, base=first)          # a partial round's own time doesn't count
    assert runner._partial_ok(on, CTX, {3}, later, 40)


def _layouts(tmp_path, full_pages):
    deck = Deck(make_deck(tmp_path, slides=[[text_box(f"s{i}")] for i in range(1, 4)]))
    base = PdfLayout(deck, renderer=None)
    base._pages = {1: [_line("a")], 2: [_line("b")], 3: [_line("c")]}
    base._src = {n: (base, "base.pdf", n) for n in (1, 2, 3)}
    return deck, base


def test_unchanged_slides_keep_the_earlier_render(tmp_path, monkeypatch):
    deck, base = _layouts(tmp_path, None)
    lay = PdfLayout(deck, renderer=None, only={2}, base=base)
    monkeypatch.setattr(lay, "_pdf_pages", lambda path, label: ("changed.pdf", {1: [_line("b2")]}))
    lay._load()
    assert [l.words for n in (1, 2, 3) for l in lay._pages[n]] == [["a"], ["b2"], ["c"]]
    assert lay._src[1][0] is base and lay._src[2][0] is lay


def test_check_mode_uses_the_full_export_and_reports_differences(tmp_path, monkeypatch):
    deck, base = _layouts(tmp_path, None)
    lay = PdfLayout(deck, renderer=None, only={2}, base=base, check=True)
    calls = iter([("changed.pdf", {1: [_line("b2")]}),
                  ("full.pdf", {1: [_line("a")], 2: [_line("b2", top=50000)], 3: [_line("c")]})])
    monkeypatch.setattr(lay, "_pdf_pages", lambda path, label: next(calls))
    lay._load()
    assert lay.partial_mismatch == [2]
    assert lay._pages[2][0].top == 50000, "the full export wins in check mode"


def test_hint_only_when_the_saving_is_big():
    events = []
    off = SimpleNamespace(partial_export="off")
    runner._partial_hint(off, CTX, [(1, 40.0, 60), (2, 40.0, 3), (3, 40.0, 1)], 60, events.append)
    assert events and events[0]["type"] == "partial_export_hint" and events[0]["seconds"] >= 30
    events.clear()
    runner._partial_hint(off, CTX, [(1, 10.0, 60), (2, 10.0, 3)], 60, events.append)
    assert not events, "a quick deck isn't worth suggesting it"
