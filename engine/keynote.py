"""Keynote → PowerPoint on the Mac (David 2026-10-11): Keynote itself exports a private copy to .pptx, then the
deck goes through the normal checks. Windows has no Keynote: .key files get a plain "convert on a Mac" message.

Which Keynote: Keynote Creator Studio (com.apple.Keynote) first, then classic Keynote (com.apple.iWork.Keynote).
Classic Keynote 14.5 shows "Use the New Version of Keynote" on EVERY launch, which blocks automation; Creator
Studio shows a one-time welcome/license screen that the user clicks through once (2026-10-11).

Like the PowerPoint renderer: work on a copy inside Keynote's own sandbox folder (no file-access prompts),
confirm the opened document's path before exporting, never touch the user's other documents, and quit
Keynote afterwards only if this run launched it. Keynote stays VISIBLE: its prompts are what blocks a
conversion, so the user must be able to see and answer one. A time limit by size turns a stuck prompt
into a plain message instead of a long wait. Conversions are cached (path + size + modified time) so the
scan and the later repair convert once.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

APPS = [("com.apple.Keynote", "Keynote Creator Studio"), ("com.apple.iWork.Keynote", "Keynote")]
CACHE = Path.home() / "Library/Caches/SlideTistic/keynote"


class KeynoteError(Exception):
    pass


def keynote_app() -> tuple[str, str] | None:
    """(bundle id, name) of the Keynote to use, or None."""
    if sys.platform != "darwin":
        return None
    for bundle, name in APPS:
        found = subprocess.run(["mdfind", f"kMDItemCFBundleIdentifier == '{bundle}'"], capture_output=True, text=True)
        if any(line.endswith(".app") and Path(line).exists() for line in found.stdout.splitlines()) \
                or bundle in _installed_bundles():
            return bundle, name
    return None


def _installed_bundles() -> set[str]:
    """Bundle ids of the Keynote apps in the Applications folders, read from their Info.plist. For Macs
    where Spotlight is off or still indexing (mdfind then finds nothing)."""
    import plistlib
    out = set()
    for folder in (Path("/Applications"), Path.home() / "Applications"):
        for app in folder.glob("*Keynote*.app"):
            try:
                with open(app / "Contents/Info.plist", "rb") as f:
                    out.add(plistlib.load(f).get("CFBundleIdentifier", ""))
            except (OSError, ValueError, plistlib.InvalidFileException):
                continue
    return out


def unavailable_reason() -> str | None:
    if sys.platform != "darwin":
        return ("Keynote files can only be converted on a Mac. Open it in Keynote, choose File ▸ Export To ▸ "
                "PowerPoint, and check the .pptx.")
    if keynote_app() is None:
        return "Keynote isn't installed on this Mac. Install it from the App Store, or export the deck to PowerPoint."
    return None


def _looks_like_keynote(key: Path) -> bool:
    """Modern .key files are zip archives; older ones are folders holding an index. Checked before
    launching Keynote, so a damaged or half-synced file gets a plain message instead of a Keynote error."""
    import zipfile
    if key.is_dir():
        return any((key / n).exists() for n in ("Index.zip", "index.apxl.gz", "Index", "index.apxl"))
    return key.is_file() and key.stat().st_size > 0 and zipfile.is_zipfile(key)


def _cache_key(key: Path) -> str:
    st = key.stat()
    return hashlib.sha1(f"{key.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]


def _running(bundle: str) -> bool:
    r = subprocess.run(["osascript", "-e", "on run argv\nreturn application id (item 1 of argv) is running\nend run", bundle],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"


def convert(key: Path) -> Path:
    """The .pptx Keynote exports from `key` (cached). Raises KeynoteError with a plain message."""
    reason = unavailable_reason()
    if reason:
        raise KeynoteError(reason)
    key = Path(key)
    if not _looks_like_keynote(key):
        raise KeynoteError(f"{key.name} isn't a valid Keynote file (it may be damaged or still downloading).")
    purge_cache()                           # conversions older than a day
    cached = CACHE / f"{_cache_key(key)}.pptx"
    if cached.exists():
        return cached
    bundle, name = keynote_app()
    work = Path.home() / "Library/Containers" / bundle / "Data/tmp/slidetistic" / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    tag = f"slidetistic-{uuid.uuid4().hex[:8]}"
    src, out = work / f"{tag}.key", work / f"{tag}.pptx"
    try:
        if key.is_dir():                    # older .key files are folders
            shutil.copytree(key, src, symlinks=True)    # links copied as links: never pull in files from elsewhere
        else:
            shutil.copyfile(key, src)
        size_mb = (sum(f.lstat().st_size for f in src.rglob("*")) if src.is_dir() else src.stat().st_size) / 1e6
        seconds = int(min(600, 60 + size_mb / 2))
        was_running = _running(bundle)
        script = f'''
        on run argv
          -- The bundle id is from APPS (ours) and must be literal for Keynote's terms to compile; paths
          -- come in as arguments.
          set src to item 1 of argv
          with timeout of {seconds} seconds
            tell application id "{bundle}"
              set d to open POSIX file src
              -- Only the document we just opened, confirmed by its path; nothing else of the user's.
              if POSIX path of ((file of d) as alias) is not src then error "Keynote opened a different document"
              export d to POSIX file (item 2 of argv) as Microsoft PowerPoint
              close d saving no
            end tell
          end timeout
        end run'''
        try:
            run = subprocess.run(["osascript", "-e", script, str(src), str(out)], capture_output=True, text=True,
                                 timeout=seconds + 30)
        except subprocess.TimeoutExpired:
            run = None
        if run is None or "-1712" in (run.stderr or ""):
            # Left running on purpose: the prompt that's waiting is what the user needs to see.
            raise KeynoteError(f"{name} didn't respond within {seconds} s. It may be showing a welcome, update or "
                               f"missing-font prompt: open {name}, answer it, then check the deck again.")
        if not was_running:
            subprocess.run(["osascript", "-e", "on run argv\ntell application id (item 1 of argv) to quit\nend run", bundle],
                           capture_output=True, timeout=30)
        if run.returncode or not out.exists():
            raise KeynoteError(f"{name} couldn't convert {key.name}: {(run.stderr or '').strip()[:200]}")
        CACHE.mkdir(parents=True, exist_ok=True)
        shutil.move(str(out), cached)
        return cached
    finally:
        shutil.rmtree(work, ignore_errors=True)


def purge_cache(max_age_hours: float = 24.0, everything: bool = False) -> int:
    """Delete converted decks older than `max_age_hours` (or all); returns bytes freed."""
    import time
    freed = 0
    if CACHE.is_dir():
        for f in CACHE.glob("*.pptx"):
            if everything or time.time() - f.stat().st_mtime > max_age_hours * 3600:
                freed += f.stat().st_size
                f.unlink(missing_ok=True)
    return freed
