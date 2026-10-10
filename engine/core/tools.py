"""Outside programs the engine runs: Poppler (pdftoppm, pdftotext) and ffprobe.

Lookup order: SLIDETISTIC_<NAME> (one program), then SLIDETISTIC_TOOLS (the folder the packaged app
ships them in), then PATH (dev machines with Homebrew).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def find(name: str) -> str | None:
    if os.environ.get(f"SLIDETISTIC_{name.upper()}"):
        return os.environ[f"SLIDETISTIC_{name.upper()}"]
    folder = os.environ.get("SLIDETISTIC_TOOLS")
    if folder:
        exe = Path(folder) / (name + (".exe" if sys.platform == "win32" else ""))
        if exe.exists():
            return str(exe)
    return shutil.which(name)
