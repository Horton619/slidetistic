"""PowerPoint copies are never left open (2026-10-13 review, items 1.1, 1.2, 1.7): the export script closes
our copy on any error, a stopped engine's copy is closed by the next one, a stop signal waits for the
export in progress, and the app hears heartbeats while PowerPoint works. No real PowerPoint here."""
import json
import subprocess
import time
from pathlib import Path

import pytest

from engine import render
from engine.core import events
from tests.fixtures.builders import make_deck, text_box


@pytest.fixture
def mac(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "OPEN_FILE", tmp_path / "open.json")
    monkeypatch.setattr(render, "STUCK_FILE", tmp_path / "stuck.json")
    r = render.MacPowerPointRenderer.__new__(render.MacPowerPointRenderer)
    r.work = tmp_path
    r._keep_hidden = lambda: False
    return r


def _ok(rc=0, err=""):
    return subprocess.CompletedProcess([], rc, "", err)


def test_export_script_takes_paths_as_arguments_and_closes_on_error(mac, monkeypatch):
    seen = {}

    def osa(script, timeout, args=(), on_start=None):
        seen.update(script=script, args=args)
        on_start(4242)
        assert json.loads(render.OPEN_FILE.read_text())["copies"][0]["pid"] == 4242
        return _ok()
    monkeypatch.setattr(mac, "_osa", osa)
    src = Path('/x/it\'s "odd".pptx')
    mac._save_as_pdf(src, Path("/x/out.pdf"), 60)
    assert seen["args"] == (str(src), "/x/out.pdf", src.name, src.stem)
    assert "odd" not in seen["script"]
    assert "on error msg number n" in seen["script"] and "close presentation (item 3 of argv)" in seen["script"]
    assert not render.OPEN_FILE.exists(), "a finished export leaves nothing in the open list"


def test_failed_export_closes_the_copy_and_clears_the_journal(mac, monkeypatch):
    closed = []
    monkeypatch.setattr(mac, "_osa", lambda s, t, args=(), on_start=None: (on_start(1), _ok(1, "PowerPoint got an error"))[1])
    monkeypatch.setattr(mac, "_close_copy", lambda src: closed.append(src) or True)
    mac._save_as_pdf(Path("/x/a.pptx"), Path("/x/a.pdf"), 60)
    assert closed == [Path("/x/a.pptx")]
    assert not render.OPEN_FILE.exists() and not render.STUCK_FILE.exists()


def test_timed_out_export_moves_from_open_list_to_stuck_list(mac, monkeypatch):
    monkeypatch.setattr(mac, "_osa", lambda s, t, args=(), on_start=None: (on_start(1), _ok(1, "AppleEvent timed out (-1712)"))[1])
    mac._save_as_pdf(Path("/x/a.pptx"), Path("/x/a.pdf"), 60)
    assert render.OPEN_FILE.exists(), "a hung export stays listed until the stuck list takes it"
    render._mark_stuck(Path("/x/a.pptx"))
    assert not render.OPEN_FILE.exists()
    assert json.loads(render.STUCK_FILE.read_text())["copies"] == ["/x/a.pptx"]


def test_next_engine_waits_for_a_running_export_then_closes_its_copy(mac, monkeypatch):
    import threading
    slow = subprocess.Popen(["sleep", "1"])         # the stopped engine's osascript, still running
    threading.Thread(target=slow.wait, daemon=True).start()     # reaped as launchd would (no zombie)
    render._journal(Path("/x/left.pptx"), slow.pid, time.time() + 30)
    closed = []

    def close(src):
        assert slow.poll() is not None, "must not touch PowerPoint while the old export is still running"
        closed.append(src)
        return True
    monkeypatch.setattr(mac, "_close_copy", close)
    t0 = time.monotonic()
    mac._close_leftovers()
    slow.wait()
    assert closed == [Path("/x/left.pptx")] and 0.5 <= time.monotonic() - t0 < 10
    assert not render.OPEN_FILE.exists()


def test_leftover_powerpoint_wont_close_becomes_stuck(mac, monkeypatch):
    render._journal(Path("/x/left.pptx"), None, 0)
    monkeypatch.setattr(mac, "_close_copy", lambda src: False)
    mac._close_leftovers()
    assert json.loads(render.STUCK_FILE.read_text())["copies"] == ["/x/left.pptx"]


def test_stop_signal_waits_for_the_export(monkeypatch):
    got = []
    monkeypatch.setattr(events, "_sink", got.append)
    monkeypatch.setattr(events, "_stop_pending", False)
    with pytest.raises(SystemExit) as stop:
        with events.busy("exporting"):
            events._on_stop(15, None)          # arrives mid-export: held
            got.append("export finished")
    assert stop.value.code == 143
    assert got == [{"type": "render", "busy": True, "what": "exporting"}, "export finished",
                   {"type": "render", "busy": False}]
    monkeypatch.setattr(events, "_stop_pending", False)
    with pytest.raises(SystemExit):
        events._on_stop(15, None)              # idle: stops at once


def test_heartbeat_while_powerpoint_works(monkeypatch):
    got = []
    monkeypatch.setattr(events, "_sink", got.append)
    with events.heartbeat("exporting", interval=0.05):
        time.sleep(0.3)
    assert got and all(e == {"type": "heartbeat", "what": "exporting"} for e in got)


def test_to_pdf_marks_the_export_busy(tmp_path, monkeypatch):
    got = []
    monkeypatch.setattr(events, "_sink", got.append)
    monkeypatch.setattr(render, "LOCK_FILE", tmp_path / "render.lock")
    deck = make_deck(tmp_path, text_box("Hello"))

    class Fake(render._Renderer):
        work = tmp_path

        def _export(self, pptx, label):
            assert events.is_busy()
            out = tmp_path / "x.pdf"
            out.write_bytes(b"%PDF")
            return out
    Fake().to_pdf(deck, "t")
    assert got[0]["type"] == "render" and got[0]["busy"] and got[-1] == {"type": "render", "busy": False}


def test_open_at_slide_waits_for_the_render_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "LOCK_FILE", tmp_path / "render.lock")
    calls = []
    monkeypatch.setattr(render.MacPowerPointRenderer, "_osa",
                        staticmethod(lambda s, t, args=(): calls.append(args) or _ok()))
    with render._render_lock():
        assert "busy" in render.open_at_slide(tmp_path / "d.pptx", 3, wait=0.2)
    assert calls == []
    assert render.open_at_slide(tmp_path / "d.pptx", 3) is None
    assert calls[0][1] == "3"


def test_repair_prompt_gets_a_plain_message_and_isnt_stuck(mac, monkeypatch, tmp_path):
    """Adversarial round 2: PowerPoint asked to repair a damaged deck. Say so plainly; it's the deck's problem, so
    PowerPoint isn't marked stuck and the next deck still gets its layout pass."""
    monkeypatch.setattr(render, "write_render_copy", lambda src, dst: dst.write_bytes(b"PK"))
    monkeypatch.setattr(render, "_deck_size", lambda p: (1, 0.1))
    monkeypatch.setattr(mac, "_close_leftovers", lambda: None)
    for stderr in ("execution error: REPAIR-PROMPT: PowerPoint had to repair the copy (-2700)",
                   "Can't get full name of missing value. (-1728)", "User canceled. (-128)"):
        monkeypatch.setattr(mac, "_save_as_pdf", lambda s, p, t, e=stderr: _ok(1, e))
        with pytest.raises(render.RenderError, match="damaged parts"):
            mac._export(tmp_path / "deck.pptx", "t")
        assert not render.STUCK_FILE.exists()
