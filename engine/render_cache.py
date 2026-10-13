"""PowerPoint's PDFs kept between runs (review 2026-10-13, 3.2), and a replay renderer for tests.

A render depends on the deck's content and on what draws it: the platform, PowerPoint's version, Poppler's
version (it reads the PDF) and the fonts installed. The key covers all five, so a re-check of an unchanged deck
reuses the PDF and skips PowerPoint, and anything that could change the drawing makes a new key.

SLIDETISTIC_RENDER_CACHE: "on" (default), "off", or "check" (export anyway and stop if the cached PDF's text
differs: proves the key is complete). SLIDETISTIC_RENDER_RECORD=<folder> also saves every export there by
content alone, and SLIDETISTIC_RENDER_REPLAY=<folder> renders only from such a folder (tests, CI: no PowerPoint).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

MODE = os.environ.get("SLIDETISTIC_RENDER_CACHE", "on")
MAX_BYTES = 2 * 1024 ** 3
VERSION = "1"            # bump when what a cached PDF means changes


class CacheMismatch(AssertionError):
    pass


def cache_dir() -> Path:
    if os.environ.get("SLIDETISTIC_RENDER_CACHE_DIR"):
        return Path(os.environ["SLIDETISTIC_RENDER_CACHE_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SlideTistic" / "Cache" / "renders"
    return Path.home() / "Library" / "Caches" / "SlideTistic" / "renders"


@lru_cache(maxsize=1)
def powerpoint_version() -> str:
    if sys.platform == "win32":
        try:
            import win32api
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\powerpnt.exe") as k:
                exe = winreg.QueryValue(k, None)
            info = win32api.GetFileVersionInfo(exe, "\\")
            ms, ls = info["FileVersionMS"], info["FileVersionLS"]
            return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
        except Exception:  # noqa: BLE001 — unknown version: never reuse a cached render
            return f"unknown-{time.time()}"
    import plistlib
    try:
        info = plistlib.loads(Path("/Applications/Microsoft PowerPoint.app/Contents/Info.plist").read_bytes())
        return f"{info.get('CFBundleShortVersionString')} ({info.get('CFBundleVersion')})"
    except (OSError, ValueError):
        return f"unknown-{time.time()}"


@lru_cache(maxsize=1)
def poppler_version() -> str:
    from .core import tools
    try:
        r = subprocess.run([tools.find("pdftotext") or "pdftotext", "-v"], capture_output=True, text=True, timeout=20)
        return (r.stderr or r.stdout).strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return f"unknown-{time.time()}"


def fonts_fingerprint() -> str:
    """Every font file this computer could draw with (name, size, modified time). ~1,000 files: a few ms.
    Not cached: fonts arrive mid-session (Get fonts, Creative Cloud activation)."""
    from .core import fonts_install
    h = hashlib.sha1()
    dirs = list(fonts_install.font_dirs())
    cc = fonts_install.creative_cloud_dir()
    if cc is not None:
        dirs.append(cc)
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*")):
            try:
                st = p.stat()
            except OSError:
                continue
            if p.is_file():
                h.update(f"{p}|{st.st_size}|{int(st.st_mtime)}\n".encode())
    return h.hexdigest()


def key_for(pptx: Path, renderer_name: str) -> str:
    from .render import content_key
    parts = [VERSION, sys.platform, renderer_name, powerpoint_version(), poppler_version(), fonts_fingerprint(),
             content_key(pptx)]
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def lookup(key: str) -> Path | None:
    if MODE == "off":
        return None
    p = cache_dir() / f"{key}.pdf"
    if p.exists():
        os.utime(p)              # recently used: kept longest
        return p
    return None


def store(key: str, pdf: Path) -> None:
    if MODE == "off":
        return
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{key}.partial"
    shutil.copyfile(pdf, tmp)
    os.replace(tmp, d / f"{key}.pdf")
    _trim(d)


def _trim(d: Path) -> None:
    files = sorted(d.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    while files and total > MAX_BYTES:
        old = files.pop(0)
        total -= old.stat().st_size
        old.unlink(missing_ok=True)


def same_text(a: Path, b: Path) -> bool:
    """check mode: two PDFs of the same key must give the same words in the same places."""
    from .core import tools
    run = lambda p: subprocess.run([tools.find("pdftotext") or "pdftotext", "-bbox", str(p), "-"],  # noqa: E731
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120).stdout
    return run(a).split("</head>", 1)[-1] == run(b).split("</head>", 1)[-1]


def record(pptx: Path, pdf: Path) -> None:
    folder = os.environ.get("SLIDETISTIC_RENDER_RECORD")
    if folder:
        from .render import content_key
        Path(folder).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, Path(folder) / f"{content_key(pptx)}.pdf")


class ReplayRenderer:
    """Draws nothing: hands back PDFs recorded from real PowerPoint by content (tests, CI). A deck that wasn't
    recorded is a RenderError saying so, so a test fails plainly when the engine's fixes change."""
    name = "replay"

    def __init__(self, folder: str | os.PathLike | None = None):
        import tempfile
        self.folder = Path(folder or os.environ["SLIDETISTIC_RENDER_REPLAY"])
        self.work = Path(tempfile.mkdtemp(prefix="slidetistic-replay-"))

    @staticmethod
    def available() -> tuple[bool, str]:
        return bool(os.environ.get("SLIDETISTIC_RENDER_REPLAY")), "no recorded renders"

    def to_pdf(self, pptx: Path, label: str) -> Path:
        from .render import RenderError, content_key
        src = self.folder / f"{content_key(pptx)}.pdf"
        if not src.exists():
            raise RenderError(f"no recorded render for {Path(pptx).name} ({label}); record again with real PowerPoint")
        out = self.work / f"{label}-{src.name}"
        shutil.copyfile(src, out)
        return out

    def page_image(self, pdf: Path, page: int, width: int = 960) -> bytes:
        from .render import _Renderer
        return _Renderer.page_image(self, pdf, page, width)

    def cleanup(self):
        shutil.rmtree(self.work, ignore_errors=True)
