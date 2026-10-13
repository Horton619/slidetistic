# -*- mode: python ; coding: utf-8 -*-
# Build from the repo root:  venv/bin/pyinstaller --clean --noconfirm backend/slidetistic_engine.spec
# One folder, not one file: the app starts the engine once per deck, and a one-file build unpacks
# ~40 MB to a temp folder on every start.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))      # collect_submodules imports `engine` to list it

# The registry finds checks by scanning engine/checks for .py files and the rules are YAML read from
# disk, so both folders ship as real files. Checks are imported dynamically, so PyInstaller can't see
# what they import: collect every engine module up front.
datas = [(str(ROOT / "engine" / "checks"), "engine/checks"),
         (str(ROOT / "engine" / "rules"), "engine/rules"),
         (str(ROOT / "engine" / "assets"), "engine/assets")]
hidden = collect_submodules("engine")
hidden += ["truststore", "certifi"]     # HTTPS for the free-font downloader (F009): the OS trust store, then certifi
assert any(m.startswith("engine.checks.") for m in hidden), "engine modules not found"

a = Analysis(
    [str(ROOT / "backend" / "slidetistic_engine.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hidden,
    excludes=["pytest", "tkinter", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="slidetistic_engine",
          console=True, upx=False, codesign_identity=None, entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, name="slidetistic_engine", upx=False)
