"""Engine → app events from anywhere in the engine, plus the "PowerPoint is busy" state.

The CLI installs the sink (one JSON line per event). Writes are locked because heartbeats come from a
second thread. `busy()` marks an export in progress: the app doesn't stop an engine mid-export, a stop
signal that arrives during one is held until it ends (stopping then would leave our copy open in
PowerPoint), and a heartbeat keeps the app's stall guard from firing while PowerPoint is slow.
"""
from __future__ import annotations

import signal
import sys
import threading
from contextlib import contextmanager

HEARTBEAT_S = 15.0

_lock = threading.Lock()
_sink = None
_busy = 0
_stop_pending = False


def set_sink(fn) -> None:
    global _sink
    _sink = fn


def emit(event: dict) -> None:
    if _sink is None:
        return
    with _lock:
        _sink(event)


@contextmanager
def heartbeat(what: str, interval: float = HEARTBEAT_S):
    """Emit {"type": "heartbeat", "what": …} every `interval` seconds while the block runs."""
    done = threading.Event()

    def beat():
        while not done.wait(interval):
            emit({"type": "heartbeat", "what": what})
    t = threading.Thread(target=beat, daemon=True)
    t.start()
    try:
        yield
    finally:
        done.set()
        t.join(1)


@contextmanager
def busy(what: str):
    """An export in progress: tell the app, hold stop signals, beat."""
    global _busy
    _busy += 1
    if _busy == 1:
        emit({"type": "render", "busy": True, "what": what})
    try:
        with heartbeat(what):
            yield
    finally:
        _busy -= 1
        if _busy == 0:
            emit({"type": "render", "busy": False})
            if _stop_pending:
                raise SystemExit(143)


def is_busy() -> bool:
    return _busy > 0


def _on_stop(signum, frame):
    global _stop_pending
    if _busy:
        _stop_pending = True        # finish this export (and close our copy), then stop
        return
    raise SystemExit(128 + signum)


def install_stop_handler() -> None:
    """SIGTERM (the app stopping a job) ends the engine cleanly, after any export in progress."""
    if sys.platform != "win32" and threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _on_stop)
