"""Render slides as PowerPoint draws them: PowerPoint → PDF → PNG (pdftoppm).

Mac: AppleScript `save … as save as PDF` (~1 s per deck). AppleScript PNG export reports success but
writes nothing on current Mac PowerPoint (2026-10-09), hence PDF. Mac PowerPoint is sandboxed: work
files live in its container so no file-access prompts appear. Windows (COM) comes with phase 4.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path

CONTAINER_TMP = Path.home() / "Library/Containers/com.microsoft.Powerpoint/Data/tmp/slidetistic"
MAC_APP = Path("/Applications/Microsoft PowerPoint.app")


class RenderError(Exception):
    pass


def pdftoppm_path() -> str | None:
    import os
    return os.environ.get("SLIDETISTIC_PDFTOPPM") or shutil.which("pdftoppm")


class PowerPointRenderer:
    name = "PowerPoint for Mac"

    @staticmethod
    def available() -> tuple[bool, str]:
        if sys.platform != "darwin":
            return False, "visual review needs PowerPoint for Mac (Windows support comes later)"
        if not MAC_APP.exists():
            return False, "PowerPoint isn't installed"
        if not pdftoppm_path():
            return False, "pdftoppm (Poppler) isn't installed"
        return True, ""

    def __init__(self):
        self.work = CONTAINER_TMP / uuid.uuid4().hex[:8]
        self.work.mkdir(parents=True, exist_ok=True)

    def to_pdf(self, pptx: Path, label: str) -> Path:
        # A unique file name AND matching by full path: an earlier version opened "after.pptx" while
        # David had his own "after.pptx" open, so PowerPoint handed back (and we closed) HIS
        # presentation (2026-10-10). Never refer to a presentation by name alone.
        tag = f"slidetistic-{uuid.uuid4().hex[:8]}-{label}"
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

    def page_image(self, pdf: Path, page: int, width: int = 960) -> bytes:
        """JPEG: a 30-slide report with PNGs was 15.7 MB; reports must open instantly on a show laptop."""
        out = self.work / f"{pdf.stem}-p{page}"
        subprocess.run([pdftoppm_path(), "-jpeg", "-jpegopt", "quality=82", "-singlefile", "-f", str(page), "-l", str(page),
                        "-scale-to-x", str(width), "-scale-to-y", "-1", str(pdf), str(out)],
                       check=True, capture_output=True, timeout=120)
        return out.with_suffix(".jpg").read_bytes()

    def cleanup(self):
        shutil.rmtree(self.work, ignore_errors=True)
