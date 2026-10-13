"""PowerPoint renderers (engine/render.py) and the pdftotext parsing they feed.

Real PowerPoint can't run in CI: the `powerpoint` test is skipped unless asked for
(`pytest -m powerpoint`, on a Mac or Windows machine with PowerPoint and Poppler).
"""
import json
import sys

import pytest

from engine import render
from engine.core import Deck
from engine.core.layout.pdf import EMU_PER_PT, PdfLayout, assign, drawn_text, parse_bbox_html
from tests.fixtures.builders import make_deck, text_box

# Windows PowerPoint keeps off-slide text in its PDF; pdftotext reports the line with a negative xMin and
# clips the straddling word ("cuatro" → "ro"). Captured from the Windows probe deck, 2026-10-10.
WIN_HALF_OFF_LEFT = """<doc><page width="1440.000000" height="810.000000"><flow><block xMin="-4.768088" yMin="366.088280" xMax="369.413200" yMax="406.255040">
<line xMin="-4.768088" yMin="366.088280" xMax="369.413200" yMax="406.255040">
<word xMin="-4.768088" yMin="366.088280" xMax="27.257248" yMax="406.255040">ro</word>
<word xMin="37.271920" yMin="366.088280" xMax="121.351936" yMax="406.255040">cinco</word>
<word xMin="131.150464" yMin="366.088280" xMax="195.201136" yMax="406.255040">seis</word>
<word xMin="205.215808" yMin="366.088280" xMax="281.298496" yMax="406.255040">siete</word>
<word xMin="291.313168" yMin="366.088280" xMax="369.413200" yMax="406.255040">ocho</word>
</line></block></flow></page></doc>"""


def test_bbox_parser_keeps_lines_that_start_off_the_slide():
    lines = parse_bbox_html(WIN_HALF_OFF_LEFT)[1]
    assert len(lines) == 1
    assert lines[0].left == pytest.approx(-4.768088 * EMU_PER_PT)
    assert lines[0].tokens == ["ro", "cinco", "seis", "siete", "ocho"]


def test_clipped_edge_word_is_not_counted_as_drawn():
    lines = parse_bbox_html(WIN_HALF_OFF_LEFT)[1]
    st = assign(lines, [(7, ["uno dos tres cuatro cinco seis siete ocho"], None)])[7]
    assert [w for l in st.lines for w in l.tokens] == ["cinco", "seis", "siete", "ocho"]


def test_platform_switch():
    expected = {"win32": render.WindowsPowerPointRenderer}.get(sys.platform, render.MacPowerPointRenderer)
    assert render.PowerPointRenderer is expected


def test_unique_work_names():
    a, b = render._unique_name("layout"), render._unique_name("layout")
    assert a != b and a.startswith("slidetistic-") and a.endswith("-layout")


@pytest.mark.skipif(sys.platform == "win32", reason="checks the message shown on other platforms")
def test_windows_renderer_explains_itself_elsewhere():
    ok, why = render.WindowsPowerPointRenderer.available()
    assert not ok and "PowerPoint" in why


def test_com_error_message_is_short_and_plain():
    class FakeComError(Exception):
        excepinfo = (0, "Microsoft PowerPoint", "PowerPoint can't open\r\n  this   file.", None, 0, -1)
    assert render._com_message(FakeComError()) == "PowerPoint can't open this file."
    assert render._com_message(ValueError("plain")) == "plain"


@pytest.mark.powerpoint
def test_real_powerpoint_render(tmp_path):
    """Hidden slides left out; words outside the slide not drawn; page = slide; input untouched."""
    ok, why = render.PowerPointRenderer.available()
    if not ok:
        pytest.skip(why)
    path = make_deck(tmp_path, slides=[
        [text_box("one two three", x=1, w=6)],
        [text_box("hidden words", x=1, w=6)],
        [text_box("alpha beta gamma delta", x=-9, w=6), text_box("café façade", x=1, y=3, w=6)],
    ], hidden=(2,))
    deck, before = Deck(path), path.read_bytes()
    r = render.PowerPointRenderer()
    try:
        layout = PdfLayout(deck, r)
        layout._load()
        assert sorted(layout._pages) == [1, 3]
        shapes = {sv.shape.text_frame.text: sv for sv in deck.iter_shapes() if sv.text_bearing}
        tol = 0.05 * 914400
        assert drawn_text(layout, deck, shapes["one two three"], tol).drawn == 3
        assert drawn_text(layout, deck, shapes["alpha beta gamma delta"], tol).drawn == 0
        assert drawn_text(layout, deck, shapes["café façade"], tol).drawn == 2
        assert r.page_image(r.to_pdf(path, "img"), 1)[:2] == b"\xff\xd8"
    finally:
        r.cleanup()
    assert path.read_bytes() == before


def test_powerpoint_failing_mid_repair_keeps_the_other_fixes(tmp_path, monkeypatch):
    """A render error (Windows: PowerPoint stopped responding) used to escape the fit pass and crash the
    whole repair. Now the layout fixes are skipped with a warning and every other fix still lands."""
    from engine.core import registry
    from engine.core import runner
    from engine.core.runner import RunConfig, repair

    class Failing:
        name = "failing"

        @staticmethod
        def available():
            return True, ""

        def to_pdf(self, pptx, label):
            raise render.RenderError("PowerPoint stopped responding")

    monkeypatch.setattr(render, "PowerPointRenderer", Failing)
    monkeypatch.setattr(runner, "_RENDERER", None)
    src = make_deck(tmp_path, text_box("Title", font="Roboto Bold"), text_box("Body", font="Roboto"))
    events = []
    result = repair(src, registry.discover(), RunConfig(layout=True), out_path=tmp_path / "out.pptx", emit=events.append)
    assert result.output_path.exists()
    assert any(c.check_id == "F001" for c in result.changes)                      # font fix still applied
    assert not any(c.check_id.startswith("L") for c in result.changes)
    assert any(e.get("type") == "warn" and "Layout fixes skipped" in e.get("message", "") for e in events)


@pytest.mark.skipif(sys.platform != "win32", reason="the COM thread needs pywin32")
def test_hung_powerpoint_call_is_abandoned_not_waited_on(monkeypatch):
    import threading
    r = render.WindowsPowerPointRenderer()
    monkeypatch.setattr(render.WindowsPowerPointRenderer, "broken", None)
    monkeypatch.setattr(r, "_on_hang", lambda: None)          # never kill anything in a test
    stuck = threading.Event()
    try:
        assert r._call(lambda: 42, 5) == 42
        with pytest.raises(render.RenderError, match="stopped responding"):
            r._call(stuck.wait, 0.2)                           # 0.2 s limit + 15 s grace, then abandoned
        assert render.WindowsPowerPointRenderer.available()[0] is False
        with pytest.raises(render.RenderError):
            r._call(lambda: 1, 5)                              # no more PowerPoint calls this run
    finally:
        stuck.set()
        r.cleanup()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process checks")
def test_stale_owned_powerpoint_record_is_dropped_without_killing_anything(tmp_path, monkeypatch):
    # A killed engine leaves a record of the PowerPoint it started; when that process is gone (or the pid
    # now belongs to something started at a different time) the record is just discarded.
    record = tmp_path / "owned-powerpoint.json"
    record.write_text('{"pid": 4000000, "started": 1}', encoding="utf-8")
    monkeypatch.setattr(render, "OWNED_FILE", record)
    assert render._close_orphaned_powerpoint() is False
    assert not record.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process checks")
def test_powerpoint_of_a_live_engine_is_never_treated_as_orphaned(tmp_path, monkeypatch):
    # Two engines can run at once (the app and a suite run): the second must not kill the first's PowerPoint.
    import os
    parent = os.getppid()
    record = tmp_path / "owned-powerpoint.json"
    record.write_text(json.dumps({"pid": 4000000, "started": 1, "engine": parent,
                                  "engine_started": render._process_started(parent)}), encoding="utf-8")
    monkeypatch.setattr(render, "OWNED_FILE", record)
    assert render._close_orphaned_powerpoint() is False
    assert record.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="pywintypes is Windows-only")
def test_busy_powerpoint_calls_are_retried_but_real_errors_are_not():
    # PC suite 2026-10-10: PowerPoint rejected pres.Close() while busy; win32com raised AttributeError("Open.Close").
    import pywintypes
    tries = []

    def busy_twice():
        tries.append(1)
        if len(tries) < 3:
            raise AttributeError("Open.Close")
        return "done"
    assert render._when_free(busy_twice, wait=5) == "done" and len(tries) == 3

    def broken():
        raise pywintypes.com_error(-2147352567, "Exception occurred.", (0, "PowerPoint", "Bad file", None, 0, 0), None)
    with pytest.raises(pywintypes.com_error):
        render._when_free(broken, wait=5)


@pytest.mark.skipif(sys.platform != "win32", reason="the COM thread needs pywin32")
def test_unexpected_powerpoint_error_becomes_a_render_error(monkeypatch):
    r = render.WindowsPowerPointRenderer()
    monkeypatch.setattr(render.WindowsPowerPointRenderer, "broken", None)
    try:
        with pytest.raises(render.RenderError, match="PowerPoint error: KeyError"):
            r._call(lambda: {}["x"], 5)
    finally:
        r.cleanup()


def test_rename_waits_out_a_brief_lock(tmp_path, monkeypatch):
    # PC suite 2026-10-11: Dropbox held review.partial a moment; the rename to review.json failed the repair.
    import os
    from engine.core import deck as deck_mod
    calls = []
    real = os.replace

    def flaky(a, b):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        real(a, b)
    monkeypatch.setattr(deck_mod.os, "replace", flaky)
    (tmp_path / "a.partial").write_text("x")
    deck_mod.replace_retrying(tmp_path / "a.partial", tmp_path / "a.json", wait=5)
    assert (tmp_path / "a.json").read_text() == "x" and len(calls) == 3


def test_any_fit_pass_failure_undoes_layout_and_reports_it(tmp_path, monkeypatch):
    """Review 2026-10-13 item 1.4: a bug inside the fit pass (not just PowerPoint failing) must not crash
    the repair. Layout changes go back, other fixes stand, and it shows as a tool_error."""
    from engine.core import registry, runner
    from engine.core.edits import EditSession
    from engine.core.deck import Deck
    from engine.core.layout import pdf as pdf_mod

    def broken(*a, **k):
        raise ValueError("unexpected PDF")
    monkeypatch.setattr(runner, "_layout_for", lambda deck, config: object())
    monkeypatch.setattr(pdf_mod, "PdfLayout", broken)
    deck = Deck(make_deck(tmp_path, text_box("Title")))
    checks = registry.discover()
    fitters = [c for c in checks if c.id.startswith("L")]
    events, errors = [], []
    runner._fit_pass(deck, fitters, EditSession(deck), runner.make_context(runner.RunConfig(layout=True)),
                     runner.RunConfig(layout=True), {}, errors, events.append)
    assert [e.check_id for e in errors] == ["L000"] and errors[0].status.value == "tool_error"
    assert any("Layout fixes were undone" in e.get("message", "") for e in events)
