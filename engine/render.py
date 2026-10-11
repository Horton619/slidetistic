"""Render slides as PowerPoint draws them: PowerPoint → PDF → JPEG (pdftoppm).

Mac: AppleScript `save … as save as PDF` (~1 s per deck). AppleScript PNG export reports success but
writes nothing on current Mac PowerPoint (2026-10-09), hence PDF. Mac PowerPoint is sandboxed: work
files live in its container so no file-access prompts appear.

Windows: COM via pywin32, `Presentations.Open(copy, ReadOnly, WithWindow=False)` → `SaveAs(pdf, 32)`
(~1 s per deck, ~3 s once to start PowerPoint). Like the Mac, the PDF leaves hidden slides out and its
pages are exactly the slide size (2026-10-10).

`PowerPointRenderer` is this platform's renderer; callers use only that name.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from .core import tools

CONTAINER_TMP = Path.home() / "Library/Containers/com.microsoft.Powerpoint/Data/tmp/slidetistic"
MAC_APP = Path("/Applications/Microsoft PowerPoint.app")


class RenderError(Exception):
    pass


def pdftoppm_path() -> str | None:
    return tools.find("pdftoppm")


def _poppler_missing() -> bool:
    return not pdftoppm_path() or not tools.find("pdftotext")


def _unique_name(label: str) -> str:
    # A unique file name, and the presentation matched by its full path: an earlier Mac version opened
    # "after.pptx" while David had his own "after.pptx" open, so PowerPoint handed back (and we closed)
    # HIS presentation (2026-10-10). Never refer to a presentation by name alone.
    return f"slidetistic-{uuid.uuid4().hex[:8]}-{label}"


class _Renderer:
    work: Path

    def page_image(self, pdf: Path, page: int, width: int = 960) -> bytes:
        """JPEG: a 30-slide report with PNGs was 15.7 MB; reports must open instantly on a show laptop."""
        out = self.work / f"{pdf.stem}-p{page}"
        subprocess.run([pdftoppm_path(), "-jpeg", "-jpegopt", "quality=82", "-singlefile", "-f", str(page), "-l", str(page),
                        "-scale-to-x", str(width), "-scale-to-y", "-1", str(pdf), str(out)],
                       check=True, capture_output=True, timeout=120)
        return out.with_suffix(".jpg").read_bytes()

    def cleanup(self):
        shutil.rmtree(self.work, ignore_errors=True)


class MacPowerPointRenderer(_Renderer):
    name = "PowerPoint for Mac"

    @staticmethod
    def available() -> tuple[bool, str]:
        if sys.platform != "darwin":
            return False, "visual review needs PowerPoint for Mac or Windows"
        if not MAC_APP.exists():
            return False, "PowerPoint isn't installed"
        if _poppler_missing():
            return False, "Poppler (pdftoppm, pdftotext) isn't installed"
        return True, ""

    def __init__(self):
        self.work = CONTAINER_TMP / uuid.uuid4().hex[:8]
        self.work.mkdir(parents=True, exist_ok=True)

    def to_pdf(self, pptx: Path, label: str) -> Path:
        tag = _unique_name(label)
        src = self.work / f"{tag}.pptx"
        pdf = self.work / f"{tag}.pdf"
        shutil.copyfile(pptx, src)
        script = f'''
        with timeout of 300 seconds
          tell application "Microsoft PowerPoint"
            open POSIX file "{src}"
            -- The file just opened is the active one (its name is unique). Confirm by full path
            -- before touching it, and never enumerate or query the user's other presentations.
            set p to active presentation
            if (full name of p) is not "{src}" then error "SlideTistic's copy isn't the active presentation"
            save p in ((POSIX file "{pdf}") as text) as save as PDF
            close p saving no
          end tell
        end timeout'''
        run = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=330)
        if run.returncode or not pdf.exists():
            raise RenderError(f"PowerPoint couldn't export {pptx.name}: {run.stderr.strip()[:200]}")
        return pdf


# --- Windows ---------------------------------------------------------------------------------------

PP_SAVE_AS_PDF = 32


def _powerpoint_pids() -> set[int]:
    """Process ids of every running POWERPNT.EXE. PowerPoint's COM object has no HWND property, so
    "is this PowerPoint ours?" is answered by which process appeared when we started it."""
    import win32api
    import win32con
    import win32process
    pids = set()
    for pid in win32process.EnumProcesses():
        try:
            h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            try:
                exe = win32process.GetModuleFileNameEx(h, None)
            finally:
                win32api.CloseHandle(h)
        except Exception:       # system processes, or gone already
            continue
        if exe.lower().endswith("\\powerpnt.exe"):
            pids.add(pid)
    return pids


def _has_visible_window(pid: int) -> bool:
    """True when the user is working in this PowerPoint (they opened a deck and it joined our instance)."""
    import win32gui
    import win32process
    found = []

    def visit(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            found.append(hwnd)
        return True
    win32gui.EnumWindows(visit, None)
    return bool(found)


# PowerPoints this engine started, by pid + creation time (a pid alone can be reused). A killed engine (the
# app stops a scan for a repair, or its stall guard fires) can't quit its PowerPoint, which then stays
# hidden holding our copy; the next engine can't tell it from the user's, and the user's next PowerPoint
# launch joins it. The next engine closes it instead: only that exact process, only with no visible window.
OWNED_FILE = Path(tempfile.gettempdir()) / "slidetistic" / "owned-powerpoint.json"


def _process_started(pid: int) -> int | None:
    import win32api
    import win32con
    import win32process
    try:
        h = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            return int(win32process.GetProcessTimes(h)["CreationTime"].timestamp())
        finally:
            win32api.CloseHandle(h)
    except Exception:
        return None


def _remember_owned(pid: int | None) -> None:
    import json
    try:
        if pid is None:
            OWNED_FILE.unlink(missing_ok=True)
        else:
            OWNED_FILE.parent.mkdir(parents=True, exist_ok=True)
            OWNED_FILE.write_text(json.dumps({"pid": pid, "started": _process_started(pid)}), encoding="utf-8")
    except OSError:
        pass


def _close_orphaned_powerpoint() -> bool:
    """Kill the PowerPoint a previous, killed engine started, if it is still that process and nobody is
    using it. True when one was closed."""
    import json
    try:
        rec = json.loads(OWNED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    pid, started = rec.get("pid"), rec.get("started")
    closed = False
    if (pid in _powerpoint_pids() and started is not None and _process_started(pid) == started
            and not _has_visible_window(pid)):
        import win32api
        import win32con
        try:
            h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
            win32api.TerminateProcess(h, 1)
            win32api.CloseHandle(h)
            closed = True
        except Exception:
            pass
    if closed or pid not in _powerpoint_pids():
        _remember_owned(None)
    return closed


def _com_message(e: Exception) -> str:
    info = getattr(e, "excepinfo", None)
    text = (info[2] if info and len(info) > 2 and info[2] else None) or str(e)
    return " ".join(str(text).split())[:200]


class WindowsPowerPointRenderer(_Renderer):
    """Safety rules (HANDOFF brief; a name clash once closed David's own deck on the Mac):
    - Only the presentation returned by OUR `Open`, confirmed by full path, is ever touched. Never
      `ActivePresentation`, never indexing or enumerating `Presentations`, never lookup by name.
    - PowerPoint is quit, or killed after a hang, only if this renderer started it, and only when no
      other deck is open in it (a deck the user opens while ours runs joins our instance).
    - Only a copy is opened, read-only. `copyfile` doesn't carry the Mark-of-the-Web: no Protected View.
    """
    name = "PowerPoint for Windows"
    timeout = 300                       # seconds per export; matches the Mac's AppleScript timeout
    broken: str | None = None           # set by a hang, for the whole engine process: stop calling PowerPoint

    @staticmethod
    def available() -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "visual review needs PowerPoint for Mac or Windows"
        import winreg
        try:
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CLSID").Close()
        except OSError:
            return False, "PowerPoint isn't installed"
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            return False, "the PowerPoint bridge (pywin32) is missing from this build"
        if _poppler_missing():
            return False, "Poppler (pdftoppm, pdftotext) isn't installed"
        if WindowsPowerPointRenderer.broken:
            return False, WindowsPowerPointRenderer.broken
        return True, ""

    def __init__(self):
        self.work = Path(tempfile.gettempdir()) / "slidetistic" / uuid.uuid4().hex[:8]
        self.work.mkdir(parents=True, exist_ok=True)
        self._app = None
        self._own_pid: int | None = None
        self._jobs = None

    # Every COM call runs on one daemon thread (COM objects belong to the thread that made them) and the
    # engine waits with a time limit. A hung call in David's own PowerPoint (seen 2026-10-10: SaveAs wrote
    # the PDF and never returned) can't be killed, so it's abandoned instead of blocking the run; the
    # daemon thread dies with the engine. A thread pool won't do: it joins its threads at exit.
    def _call(self, fn, timeout: float):
        import queue
        if WindowsPowerPointRenderer.broken:
            raise RenderError(WindowsPowerPointRenderer.broken)
        if self._jobs is None:
            self._jobs = queue.Queue()
            threading.Thread(target=self._com_thread, args=(self._jobs,), daemon=True,
                             name="powerpoint-com").start()
        done, box = threading.Event(), {}
        self._jobs.put((fn, done, box))
        if not done.wait(timeout):
            self._on_hang()
            if not done.wait(15):            # killing our own PowerPoint makes the call return at once
                WindowsPowerPointRenderer.broken = (
                    "PowerPoint stopped responding (a dialog may be open in PowerPoint), so SlideTistic "
                    "stopped using it for this deck")
                raise RenderError(WindowsPowerPointRenderer.broken)
            self._app, self._own_pid = None, None
            raise RenderError(f"PowerPoint stopped responding (over {int(timeout)} s) and was closed")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    @staticmethod
    def _com_thread(jobs):
        import pythoncom
        pythoncom.CoInitialize()
        while True:
            fn, done, box = jobs.get()
            try:
                box["value"] = fn()
            except BaseException as e:      # handed back to the waiting caller
                box["error"] = e
            done.set()

    def _powerpoint(self):
        """Runs on the COM thread."""
        import pywintypes
        import win32com.client
        if self._app is not None:
            try:
                self._app.Version            # still alive? (it may have been quit or killed)
                return self._app
            except pywintypes.com_error:
                self._app, self._own_pid = None, None
        if _close_orphaned_powerpoint():
            import time
            time.sleep(1)                    # let Windows drop its COM registration before we dispatch
        before = _powerpoint_pids()
        try:
            self._app = win32com.client.DispatchEx("PowerPoint.Application")
        except pywintypes.com_error as e:
            raise RenderError(f"PowerPoint couldn't be started: {_com_message(e)}") from e
        new = _powerpoint_pids() - before
        self._own_pid = next(iter(new)) if len(new) == 1 else None
        if self._own_pid:
            _remember_owned(self._own_pid)
        return self._app

    def _on_hang(self):
        """Kill PowerPoint only if it's ours and the user isn't in it (no visible window)."""
        pid = self._own_pid
        if pid and not _has_visible_window(pid):
            import win32api
            import win32con
            try:
                h = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                win32api.TerminateProcess(h, 1)
                win32api.CloseHandle(h)
            except Exception:
                pass

    def to_pdf(self, pptx: Path, label: str) -> Path:
        tag = _unique_name(label)
        src = self.work / f"{tag}.pptx"
        pdf = self.work / f"{tag}.pdf"
        shutil.copyfile(pptx, src)

        def export():
            import pywintypes
            app = self._powerpoint()
            try:
                pres = app.Presentations.Open(str(src), True, False, False)   # ReadOnly, Untitled, WithWindow
            except pywintypes.com_error as e:
                raise RenderError(f"PowerPoint couldn't open {pptx.name}: {_com_message(e)}") from e
            if not os.path.samefile(pres.FullName, src):
                raise RenderError("PowerPoint returned a different presentation than SlideTistic's copy")
            try:
                pres.SaveAs(str(pdf), PP_SAVE_AS_PDF)
            except pywintypes.com_error as e:
                raise RenderError(f"PowerPoint couldn't export {pptx.name}: {_com_message(e)}") from e
            finally:
                try:
                    pres.Close()
                except pywintypes.com_error:
                    pass

        self._call(export, self.timeout)
        if not pdf.exists():
            raise RenderError(f"PowerPoint couldn't export {pptx.name}")
        return pdf

    def cleanup(self):
        def quit_if_ours():
            import pywintypes
            app, self._app = self._app, None
            if app is not None and self._own_pid:
                try:
                    if app.Presentations.Count == 0:
                        app.Quit()
                        _remember_owned(None)
                except pywintypes.com_error:
                    pass
        if self._jobs is not None and not WindowsPowerPointRenderer.broken:
            try:
                self._call(quit_if_ours, 30)
            except RenderError:
                pass
        super().cleanup()


PowerPointRenderer = WindowsPowerPointRenderer if sys.platform == "win32" else MacPowerPointRenderer
