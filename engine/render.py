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

from .core import events, tools
from .core.deck import write_render_copy

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


def content_key(pptx: Path) -> str:
    """Fingerprint of what's inside a deck: each part's name, CRC and size from the zip directory.
    python-pptx stamps new zip timestamps on every save, so identical content gives different file
    bytes; this matches them without reading any media."""
    import hashlib
    import zipfile
    from .core.deck import stub_for
    with zipfile.ZipFile(pptx) as z:
        # Media that renders as its poster image counts by name only: a render copy (stand-in) and
        # the real deck draw the same.
        rows = sorted((i.filename, 0, 0) if stub_for(i.filename) is not None else (i.filename, i.CRC, i.file_size)
                      for i in z.infolist())
    return hashlib.sha1(repr(rows).encode()).hexdigest()


LOCK_FILE = Path(tempfile.gettempdir()) / "slidetistic" / "render.lock"


class _render_lock:
    """One PowerPoint export at a time across all SlideTistic processes on this computer. The app, a
    suite run and a CLI repair could all drive PowerPoint at once (2026-10-11: an overnight Mac run
    froze with ~30 exports queued inside PowerPoint)."""

    def __init__(self, wait: float = 1800.0):
        self.wait = wait

    def __enter__(self):
        import time
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(LOCK_FILE, "a+")
        deadline = time.monotonic() + self.wait
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() > deadline:
                    self.f.close()
                    raise RenderError("another SlideTistic job has been using PowerPoint for over 30 minutes")
                time.sleep(0.5)

    def __exit__(self, *exc):
        try:
            if sys.platform == "win32":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
        finally:
            self.f.close()


def _work_roots() -> list[Path]:
    """Where renderers keep their per-job folders (Mac: PowerPoint's sandbox; Windows: temp)."""
    keynote = [Path.home() / "Library/Containers" / b / "Data/tmp/slidetistic" for b in ("com.apple.Keynote", "com.apple.iWork.Keynote")]
    return [CONTAINER_TMP, Path(tempfile.gettempdir()) / "slidetistic", *keynote]


def purge_leftovers(max_age_hours: float = 6.0, everything: bool = False) -> int:
    """Delete renderer work folders a finished or killed job left behind; returns bytes freed.
    Automatic (every renderer start): folders untouched for `max_age_hours`, longer than any job runs.
    `everything` (Settings → Clear temporary files): all of them, but only while no job holds the
    render lock. Copies PowerPoint is stuck on (STUCK_FILE) are kept until it's recovered."""
    import json
    import time
    try:
        stuck = {str(Path(c).parent) for c in json.loads(STUCK_FILE.read_text(encoding="utf-8")).get("copies", [])}
    except (OSError, ValueError):
        stuck = set()
    lock = None
    if everything:
        try:
            lock = _render_lock(wait=0).__enter__()
        except RenderError:
            everything = False              # a job is rendering right now: only clear the old ones
    freed = 0
    try:
        for root in _work_roots():
            if not root.is_dir():
                continue
            for d in root.iterdir():
                if not d.is_dir() or str(d) in stuck:
                    continue
                files = [f for f in d.rglob("*") if f.is_file()]
                newest = max((f.stat().st_mtime for f in files), default=d.stat().st_mtime)
                if everything or time.time() - newest > max_age_hours * 3600:
                    freed += sum(f.stat().st_size for f in files)
                    shutil.rmtree(d, ignore_errors=True)
    finally:
        if lock:
            lock.__exit__(None, None, None)
    return freed


def _deck_size(pptx: Path) -> tuple[int, float]:
    """(slides, MB) without opening the deck in python-pptx."""
    import re
    import zipfile
    with zipfile.ZipFile(pptx) as z:
        slides = sum(1 for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
    return slides, pptx.stat().st_size / 1e6


# Where a job's time goes (review 2026-10-13, 3.8): the CLI reports these at the end ("timing" event).
STATS = {"exports": 0, "export_s": 0.0, "cache_hits": 0, "lock_wait_s": 0.0, "pages": 0, "page_s": 0.0}


class _Renderer:
    work: Path

    def to_pdf(self, pptx: Path, label: str) -> Path:
        """PowerPoint's PDF of this deck. A job asks for the same content several times (the scan's
        layout and its "before" images; a repair's last fit round, safety pass, re-scan and "after"
        images): each distinct content is exported once per renderer."""
        cache = self.__dict__.setdefault("_pdfs", {})
        key = content_key(pptx)
        if key in cache and cache[key].exists():
            return cache[key]
        # Between runs too (render_cache): the same deck drawn by the same PowerPoint, Poppler and fonts.
        from . import render_cache
        stored_key = render_cache.key_for(pptx, getattr(self, "name", type(self).__name__)) if render_cache.MODE != "off" else None
        stored = render_cache.lookup(stored_key) if stored_key else None
        if stored and render_cache.MODE != "check":
            pdf = self.work / f"{_unique_name(label)}.pdf"
            shutil.copyfile(stored, pdf)        # a copy: the cache may be trimmed while this job runs
            cache[key] = pdf
            STATS["cache_hits"] += 1
            return pdf
        import time
        t0 = time.monotonic()
        with events.heartbeat("waiting for another job's PowerPoint export"):
            lock = _render_lock().__enter__()
        t1 = time.monotonic()
        try:
            with events.busy("PowerPoint is drawing the slides"):
                pdf = self._export(pptx, label)
        finally:
            lock.__exit__(None, None, None)
        STATS["exports"] += 1
        STATS["lock_wait_s"] += t1 - t0
        STATS["export_s"] += time.monotonic() - t1
        if stored and not render_cache.same_text(stored, pdf):
            raise render_cache.CacheMismatch(f"cached render of {pptx.name} differs from a fresh one: the key misses something")
        if stored_key:
            render_cache.store(stored_key, pdf)
        render_cache.record(pptx, pdf)
        cache[key] = pdf
        return pdf

    def page_image(self, pdf: Path, page: int, width: int = 960) -> bytes:
        """JPEG: a 30-slide report with PNGs was 15.7 MB; reports must open instantly on a show laptop."""
        import time
        t0 = time.monotonic()
        out = self.work / f"{pdf.stem}-p{page}-w{width}"
        subprocess.run([pdftoppm_path(), "-jpeg", "-jpegopt", "quality=82", "-singlefile", "-f", str(page), "-l", str(page),
                        "-scale-to-x", str(width), "-scale-to-y", "-1", str(pdf), str(out)],
                       check=True, capture_output=True, timeout=120)
        STATS["pages"] += 1
        STATS["page_s"] += time.monotonic() - t0
        return Path(f"{out}.jpg").read_bytes()

    def cleanup(self):
        shutil.rmtree(self.work, ignore_errors=True)


STUCK_FILE = CONTAINER_TMP / "stuck.json"
# Mac PowerPoint has no "open without a window", so SlideTistic keeps PowerPoint hidden (like ⌘H) while
# it renders, but only when it launched PowerPoint itself or PowerPoint was already hidden: David's
# own PowerPoint windows never vanish mid-work. Default on (David 2026-10-11); `--powerpoint-visible`
# or SLIDETISTIC_PPT_HIDDEN=off turns it off if hidden renders ever stall on a dialog nobody can see.
PPT_HIDDEN = os.environ.get("SLIDETISTIC_PPT_HIDDEN", "on") != "off"
STUCK_MESSAGE = ("PowerPoint stopped responding. Save your work, quit PowerPoint (Force Quit if needed), "
                 "then check the deck again")


class MacPowerPointRenderer(_Renderer):
    """Hang handling (2026-10-11: one export froze at "Processing slide 35 of 35" and every later
    export queued behind it, 10 hours of timeouts):
    - a time limit by deck size instead of a flat 5 minutes;
    - after a hang, this process stops calling PowerPoint (`broken`, like Windows) and the next
      process learns of it from STUCK_FILE;
    - before rendering again, a 1-slide test export. If PowerPoint is still stuck and every open
      presentation is one of OUR stuck copies (checked by their unique names, never by listing the
      user's), PowerPoint is quit, force-quit if it won't. With anything of David's open, it's left
      alone and the app tells him to save and quit.
    - a hung export whose PDF is complete (every visible slide drawn) is still used."""
    name = "PowerPoint for Mac"
    broken: str | None = None
    force_quit_note: str | None = None      # shown once to the user if a force-quit was needed

    @staticmethod
    def available() -> tuple[bool, str]:
        if sys.platform != "darwin":
            return False, "visual review needs PowerPoint for Mac or Windows"
        if not MAC_APP.exists():
            return False, "PowerPoint isn't installed"
        if _poppler_missing():
            return False, "Poppler (pdftoppm, pdftotext) isn't installed"
        if MacPowerPointRenderer.broken:
            return False, MacPowerPointRenderer.broken
        return True, ""

    def __init__(self):
        purge_leftovers()
        self.work = CONTAINER_TMP / uuid.uuid4().hex[:8]
        self.work.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _osa(script: str, timeout: float, args: tuple[str, ...] = (), on_start=None) -> subprocess.CompletedProcess | None:
        """Run AppleScript. Paths and names go in as `args` (read by `on run argv`), never pasted into
        the script text, so a quote or backslash in a path can't change what the script does."""
        proc = subprocess.Popen(["osascript", "-e", script, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        if on_start:
            on_start(proc.pid)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return None
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    def _close_copy(self, src: Path) -> bool:
        """Close our copy by its unique name if PowerPoint still has it open. False: PowerPoint didn't answer."""
        if subprocess.run(["pgrep", "-x", "Microsoft PowerPoint"], capture_output=True).returncode:
            return True                 # not running: nothing is open
        r = self._osa('on run argv\nwith timeout of 20 seconds\ntell application "Microsoft PowerPoint"\n'
                      'if exists presentation (item 1 of argv) then close presentation (item 1 of argv) saving no\n'
                      'end tell\nend timeout\nend run', 30, (src.name,))
        return r is not None and r.returncode == 0

    def _close_leftovers(self) -> None:
        """Copies a stopped engine left open (OPEN_FILE). Runs inside the render lock, so every entry
        belongs to a job that's gone. If its osascript is still running (the engine was killed but the
        export carries on), wait for it to finish first: two exports at once is how PowerPoint jammed."""
        import json
        import time
        try:
            entries = json.loads(OPEN_FILE.read_text(encoding="utf-8")).get("copies", [])
        except (OSError, ValueError):
            return
        for e in entries:
            while _alive(e.get("pid")) and time.time() < e.get("until", 0):
                time.sleep(0.5)
            if not self._close_copy(Path(e["path"])):
                _mark_stuck(Path(e["path"]))
            _unjournal(Path(e["path"]))

    def _keep_hidden(self) -> bool:
        """Should PowerPoint stay hidden for this render? Yes when it isn't running (it's launched here,
        hidden) or it's already hidden; no when David has it in view. Best effort: if macOS refuses
        (System Events permission declined), the render simply happens in view."""
        if not PPT_HIDDEN:
            return False
        running = subprocess.run(["pgrep", "-x", "Microsoft PowerPoint"], capture_output=True).returncode == 0
        if running:
            vis = self._osa('tell application "System Events" to get visible of process "Microsoft PowerPoint"', 10)
            if vis is None or vis.stdout.strip() != "false":
                # Shown, but with nothing open nothing of David's is in view (counting, never listing).
                n = self._osa('with timeout of 10 seconds\ntell application "Microsoft PowerPoint" to count presentations\n'
                              'end timeout', 20)
                if n is None or n.stdout.strip() != "0":
                    return False    # David's PowerPoint is in view: leave it alone
        else:
            self._osa('tell application "Microsoft PowerPoint" to launch', 60)
        self._osa('tell application "System Events" to set visible of process "Microsoft PowerPoint" to false', 10)
        return True

    def _save_as_pdf(self, src: Path, pdf: Path, seconds: int) -> subprocess.CompletedProcess | None:
        # Opening a document shows PowerPoint again a moment AFTER `open` returns (measured: ~1 s), so wait
        # for the window, then hide; hide again after closing so the next render still sees it hidden.
        hidden = self._keep_hidden()
        rehide = ('try\n tell application "System Events" to tell process "Microsoft PowerPoint"\n'
                  '  repeat 40 times\n   if (count of windows) > 0 then exit repeat\n   delay 0.025\n  end repeat\n'
                  '  set visible to false\n end tell\nend try') if hidden else ""
        hide_after = ('try\n tell application "System Events" to set visible of process "Microsoft PowerPoint" to false\n'
                      'end try') if hidden else ""
        # On any error the copy is closed by its unique name before the error is passed on, so a failed
        # export never leaves it open in PowerPoint. Not after a timeout (-1712): PowerPoint is stuck, and
        # `_recover` deals with that.
        script = f'''
        on run argv
          set src to item 1 of argv
          -- File references are made here, outside PowerPoint's tell block: inside it, `POSIX file x` of a
          -- variable goes to PowerPoint, and the save then "succeeds" without writing anything (2026-10-13).
          set srcFile to POSIX file src
          set pdfPath to (POSIX file (item 2 of argv)) as text
          with timeout of {seconds} seconds
            tell application "Microsoft PowerPoint"
              open srcFile
            end tell
            {rehide}
            try
              tell application "Microsoft PowerPoint"
                -- The file just opened is the active one (its name is unique). Confirm by full path
                -- before touching it, and never enumerate or query the user's other presentations.
                set p to active presentation
                if (full name of p) is not src then error "SlideTistic's copy isn't the active presentation"
                save p in pdfPath as save as PDF
                close p saving no
              end tell
            on error msg number n
              if n is not -1712 then
                try
                  with timeout of 20 seconds
                    tell application "Microsoft PowerPoint"
                      if exists presentation (item 3 of argv) then close presentation (item 3 of argv) saving no
                    end tell
                  end timeout
                end try
              end if
              error msg number n
            end try
            {hide_after}
          end timeout
        end run'''
        import time
        limit = seconds + 30
        run = self._osa(script, limit, (str(src), str(pdf), src.name),
                        on_start=lambda pid: _journal(src, pid, time.time() + limit))
        if run is not None and "-1712" not in run.stderr:
            if run.returncode and not self._close_copy(src):
                _mark_stuck(src)
            _unjournal(src)
        return run

    def _export(self, pptx: Path, label: str) -> Path:
        if MacPowerPointRenderer.broken:
            raise RenderError(MacPowerPointRenderer.broken)
        self._close_leftovers()
        if STUCK_FILE.exists() and not self._recover():
            MacPowerPointRenderer.broken = STUCK_MESSAGE
            raise RenderError(STUCK_MESSAGE)
        tag = _unique_name(label)
        src = self.work / f"{tag}.pptx"
        pdf = self.work / f"{tag}.pdf"
        write_render_copy(pptx, src)      # media as stand-ins: same render, a fraction of the size
        slides, mb = _deck_size(src)
        seconds = int(min(300, 60 + 2 * slides + mb / 20))
        run = self._save_as_pdf(src, pdf, seconds)
        if run is not None and run.returncode == 0 and pdf.exists():
            return pdf
        hung = run is None or "-1712" in run.stderr       # AppleEvent timed out
        if not hung:
            raise RenderError(f"PowerPoint couldn't export {pptx.name}: "
                              f"{run.stderr.strip()[:200] or 'it reported no error but wrote no PDF'}")
        _mark_stuck(src)
        salvaged = pdf.exists() and _pdf_complete(pdf, src)
        if not self._recover():
            MacPowerPointRenderer.broken = STUCK_MESSAGE
            if not salvaged:
                raise RenderError(STUCK_MESSAGE)
        if salvaged:
            return pdf
        raise RenderError(f"PowerPoint took over {seconds} s on {pptx.name} and was restarted")

    def _probe(self) -> bool:
        """A 1-slide deck exports within 30 s: PowerPoint is answering."""
        from pptx import Presentation
        tag = _unique_name("probe")
        src, pdf = self.work / f"{tag}.pptx", self.work / f"{tag}.pdf"
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(str(src))
        run = self._save_as_pdf(src, pdf, 30)
        if run is not None and run.returncode == 0 and pdf.exists():
            return True
        _mark_stuck(src)
        return False

    def _recover(self) -> bool:
        """True when PowerPoint can be used again. Quits it only when it's stuck and everything open
        in it is SlideTistic's own stuck copies."""
        import json
        import time
        if self._probe():
            STUCK_FILE.unlink(missing_ok=True)
            return True
        try:
            copies = json.loads(STUCK_FILE.read_text(encoding="utf-8")).get("copies", [])
        except (OSError, ValueError):
            copies = []
        count = self._osa('with timeout of 10 seconds\ntell application "Microsoft PowerPoint" to count presentations\n'
                          'end timeout', 20)
        if count is None or count.returncode or not count.stdout.strip().isdigit():
            return False
        ours = 0
        for c in copies:            # by our unique random names only: never look at David's decks
            name = Path(c).name
            r = self._osa('on run argv\nwith timeout of 10 seconds\ntell application "Microsoft PowerPoint" to '
                          'exists presentation (item 1 of argv)\nend timeout\nend run', 20, (name,))
            ours += r is not None and r.stdout.strip() == "true"
        if int(count.stdout.strip()) > ours:
            return False            # something of David's is open: never quit his PowerPoint
        # Patient first (2026-10-11: a force-quit makes macOS show Microsoft's crash report). Close just
        # our stuck copies, by their unique random names, and test again.
        for c in copies:
            self._osa('on run argv\nwith timeout of 20 seconds\ntell application "Microsoft PowerPoint" to '
                      'close presentation (item 1 of argv) saving no\nend timeout\nend run', 30, (Path(c).name,))
        if self._probe():
            STUCK_FILE.unlink(missing_ok=True)
            return True
        # Then ask it to quit and give it a minute to finish what it's doing.
        self._osa('with timeout of 60 seconds\ntell application "Microsoft PowerPoint" to quit saving no\n'
                  'end timeout', 70)
        for _ in range(120):
            if subprocess.run(["pgrep", "-x", "Microsoft PowerPoint"], capture_output=True).returncode:
                break
            time.sleep(0.5)
        else:
            # Last resort; macOS will show Microsoft's crash report, so say why.
            MacPowerPointRenderer.force_quit_note = ("PowerPoint stopped responding and SlideTistic had to force-quit "
                                                     "it (only SlideTistic's copies were open). If Microsoft's crash "
                                                     "report appears, untick \"Recover work\" and click OK.")
            subprocess.run(["pkill", "-9", "-x", "Microsoft PowerPoint"], capture_output=True)
            time.sleep(2)
        STUCK_FILE.unlink(missing_ok=True)
        return self._probe()


# Copies handed to PowerPoint and not yet closed, with the osascript driving each. An entry left behind
# means the engine was stopped mid-export; the next engine closes that copy (`_close_leftovers`).
OPEN_FILE = CONTAINER_TMP / "open.json"


def _alive(pid) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _journal(src: Path, pid: int, until: float) -> None:
    import json
    try:
        data = json.loads(OPEN_FILE.read_text(encoding="utf-8")) if OPEN_FILE.exists() else {}
    except (OSError, ValueError):
        data = {}
    rows = [e for e in data.get("copies", []) if e.get("path") != str(src)]
    rows.append({"path": str(src), "pid": pid, "until": until})
    OPEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    OPEN_FILE.write_text(json.dumps({"copies": rows}), encoding="utf-8")


def _unjournal(src: Path) -> None:
    import json
    try:
        data = json.loads(OPEN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    rows = [e for e in data.get("copies", []) if e.get("path") != str(src)]
    if rows:
        OPEN_FILE.write_text(json.dumps({"copies": rows}), encoding="utf-8")
    else:
        OPEN_FILE.unlink(missing_ok=True)


def open_at_slide(deck: Path, slide: int, wait: float = 45.0) -> str | None:
    """Mac: show David a deck in PowerPoint at a slide. Takes the render lock so it never lands in the
    middle of a hidden export (the export confirms "its" copy by being the active presentation).
    Returns a plain problem, or None."""
    try:
        lock = _render_lock(wait=wait).__enter__()
    except RenderError:
        return "PowerPoint is busy drawing slides for a check. Try again in a moment."
    try:
        r = MacPowerPointRenderer._osa(
            'on run argv\nset f to POSIX file (item 1 of argv)\nwith timeout of 60 seconds\n'
            'tell application "Microsoft PowerPoint"\nactivate\nopen f\nset p to active presentation\n'
            'if (full name of p) is (item 1 of argv) then go to slide (view of document window 1) number '
            '((item 2 of argv) as integer)\nend tell\nend timeout\nend run', 90, (str(deck.resolve()), str(int(slide))))
    finally:
        lock.__exit__(None, None, None)
    if r is None:
        return "PowerPoint didn't answer within 90 seconds."
    if r.returncode:
        return r.stderr.strip()[:200] or "PowerPoint couldn't open it."
    return None


def _mark_stuck(src: Path) -> None:
    """Remember a copy PowerPoint is stuck on (it stays open in PowerPoint), for this and later runs."""
    import json
    import time
    _unjournal(src)             # the stuck list takes it over
    try:
        data = json.loads(STUCK_FILE.read_text(encoding="utf-8")) if STUCK_FILE.exists() else {}
    except (OSError, ValueError):
        data = {}
    data.setdefault("since", time.time())
    data["copies"] = sorted(set(data.get("copies", [])) | {str(src)})
    STUCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    STUCK_FILE.write_text(json.dumps(data), encoding="utf-8")


def _pdf_complete(pdf: Path, deck: Path) -> bool:
    """A PDF from a hung export is used only if it ends properly and has a page for every visible
    slide (a short PDF would make later pages' words look missing: false "off the slide" reds)."""
    import re
    import zipfile
    try:
        if not pdf.read_bytes()[-1024:].rstrip().endswith(b"%%EOF"):
            return False
        with zipfile.ZipFile(deck) as z:
            visible = sum(1 for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
                          and b'show="0"' not in z.read(n)[:400])
        out = subprocess.run([tools.find("pdftotext") or "pdftotext", "-bbox", str(pdf), "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        return out.returncode == 0 and out.stdout.count("<page ") == visible
    except (OSError, subprocess.SubprocessError):
        return False


# --- Windows ---------------------------------------------------------------------------------------

PP_SAVE_AS_PDF = 32
MSO_FORCE_DISABLE = 3          # msoAutomationSecurityForceDisable


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
            OWNED_FILE.write_text(json.dumps({"pid": pid, "started": _process_started(pid), "engine": os.getpid(),
                                              "engine_started": _process_started(os.getpid())}), encoding="utf-8")
    except OSError:
        pass


def _close_orphaned_powerpoint() -> bool:
    """Kill the PowerPoint a previous engine started, if that engine is gone (killed), the PowerPoint is
    still that same process, and nobody is using it. Never touches a live engine's PowerPoint: two engines
    can run at once (the app and a suite run). True when one was closed."""
    import json
    try:
        rec = json.loads(OWNED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    pid, started = rec.get("pid"), rec.get("started")
    engine, engine_started = rec.get("engine"), rec.get("engine_started")
    engine_alive = engine_started is not None and _process_started(engine) == engine_started
    if engine and engine != os.getpid() and engine_alive:
        return False                    # the engine that started it is still running: not an orphan
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


# PowerPoint refuses calls while it's busy (finishing an export, closing a big deck, or serving another
# client): RPC_E_CALL_REJECTED / RPC_E_SERVERCALL_RETRYLATER. win32com's late binding reports the same thing
# as AttributeError("Open.Close") when it can't look the method up. A rejected call never ran, so retrying
# is safe (PC suite run 2026-10-10 failed a repair on "Open.Close" after the safety pass).
_BUSY = {-2147418111, -2147417846}


def _when_free(call, *args, wait: float = 30.0):
    """Run one PowerPoint COM call, retrying while PowerPoint says it's busy."""
    import time
    import pywintypes
    deadline, delay = time.monotonic() + wait, 0.1
    while True:
        try:
            return call(*args)
        except (pywintypes.com_error, AttributeError) as e:
            busy = isinstance(e, AttributeError) or getattr(e, "hresult", None) in _BUSY
            if not busy or time.monotonic() > deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 2.0)


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
        purge_leftovers()
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
            e = box["error"]
            if isinstance(e, RenderError):
                raise e
            # Anything else from PowerPoint must not crash the repair: callers handle RenderError
            # (layout skipped, other fixes kept).
            raise RenderError(f"PowerPoint error: {type(e).__name__}: {_com_message(e)}") from e
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
                _when_free(lambda: self._app.Version, wait=10)   # still alive? (it may have been quit or killed)
                return self._app
            except (pywintypes.com_error, AttributeError):
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

    def _export(self, pptx: Path, label: str) -> Path:
        tag = _unique_name(label)
        src = self.work / f"{tag}.pptx"
        pdf = self.work / f"{tag}.pdf"
        write_render_copy(pptx, src)      # media as stand-ins: same render, a fraction of the size

        def export():
            import pywintypes
            app = self._powerpoint()
            # Macros never run in a file we open (review 2026-10-13, 1.3). AutomationSecurity covers files
            # opened through COM only, but the PowerPoint may be the user's, so it's put back afterwards.
            try:
                security = _when_free(lambda: app.AutomationSecurity)
                _when_free(lambda: setattr(app, "AutomationSecurity", MSO_FORCE_DISABLE))
            except (pywintypes.com_error, AttributeError):
                security = None
            try:
                # ReadOnly, Untitled, WithWindow
                pres = _when_free(lambda: app.Presentations.Open(str(src), True, False, False))
            except (pywintypes.com_error, AttributeError) as e:
                raise RenderError(f"PowerPoint couldn't open {pptx.name}: {_com_message(e)}") from e
            finally:
                if security is not None:
                    try:
                        _when_free(lambda: setattr(app, "AutomationSecurity", security))
                    except (pywintypes.com_error, AttributeError):
                        pass
            if not os.path.samefile(_when_free(lambda: pres.FullName), src):
                raise RenderError("PowerPoint returned a different presentation than SlideTistic's copy")
            try:
                _when_free(lambda: pres.SaveAs(str(pdf), PP_SAVE_AS_PDF))
            except (pywintypes.com_error, AttributeError) as e:
                raise RenderError(f"PowerPoint couldn't export {pptx.name}: {_com_message(e)}") from e
            finally:
                try:
                    _when_free(lambda: pres.Close())
                except (pywintypes.com_error, AttributeError):
                    pass                        # the PDF is written; a copy left open is closed with PowerPoint

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
                    if _when_free(lambda: app.Presentations.Count, wait=10) == 0:
                        _when_free(lambda: app.Quit(), wait=10)
                        _remember_owned(None)
                except (pywintypes.com_error, AttributeError):
                    pass
        if self._jobs is not None and not WindowsPowerPointRenderer.broken:
            try:
                self._call(quit_if_ours, 30)
            except RenderError:
                pass
        super().cleanup()


PowerPointRenderer = WindowsPowerPointRenderer if sys.platform == "win32" else MacPowerPointRenderer
if os.environ.get("SLIDETISTIC_RENDER_REPLAY"):         # tests and CI: recorded renders only (render_cache)
    from .render_cache import ReplayRenderer as PowerPointRenderer  # noqa: F811
