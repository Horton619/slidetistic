"""Download, check and install free fonts for the current user (F009, David 2026-10-12).

Files: Google Fonts' CSS API asked for TrueType (legacy user agent) for `type: google` families. It returns one
static, full-character-set file per weight/style, correctly named. Fontsource's own static files are often
misnamed (Montserrat Regular calls itself "Montserrat Thin"): docs/F009_FONTSOURCE_DESIGN.md §10. Other
families come from Fontsource's latin subset. Every file must carry the family name the deck asks for, or it
isn't installed.

Install: Mac ~/Library/Fonts; Windows %LOCALAPPDATA%\\Microsoft\\Windows\\Fonts + the HKCU font registry entry
(no admin rights). `SLIDETISTIC_FONT_DIR` overrides the folder (tests; nothing else is touched then).
What was installed is recorded in the cache's installed.json so `fonts uninstall` can take it back out.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from . import fonts_catalog, http

WEIGHTS = {"thin": 100, "hairline": 100, "extralight": 200, "ultralight": 200, "light": 300, "regular": 400,
           "normal": 400, "book": 400, "medium": 500, "semibold": 600, "demibold": 600, "bold": 700,
           "extrabold": 800, "ultrabold": 800, "black": 900, "heavy": 900}
LEGACY_UA = "Mozilla/4.0"           # Google serves TrueType to old browsers (WOFF2 to new ones)


class FontError(Exception):
    pass


# --- where fonts live --------------------------------------------------------------------------------

def install_dir() -> Path:
    if os.environ.get("SLIDETISTIC_FONT_DIR"):
        return Path(os.environ["SLIDETISTIC_FONT_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Microsoft" / "Windows" / "Fonts"
    return Path.home() / "Library" / "Fonts"


def creative_cloud_dir() -> Path | None:
    """Where Creative Cloud keeps fonts activated from Adobe Fonts (hidden files; the OS sees them while
    Creative Cloud runs). Read only, for their names (David 2026-10-12: "I have Creative Cloud")."""
    if os.environ.get("SLIDETISTIC_FONT_DIR"):
        return None
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Adobe" / "CoreSync" / "plugins" / "livetype" / "r"
    return Path.home() / "Library" / "Application Support" / "Adobe" / "CoreSync" / "plugins" / "livetype" / ".r"


def office_cloud_dirs() -> list[Path]:
    """Where Office keeps the Microsoft 365 cloud fonts it has downloaded (plain .ttf files, one folder per family:
    Abadi, Grandview, Aptos Display…). PowerPoint uses them like installed fonts (David 2026-10-15)."""
    if os.environ.get("SLIDETISTIC_FONT_DIR"):
        return []
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Microsoft" / "FontCache"
    else:
        base = Path.home() / "Library" / "Group Containers" / "UBF8T346G9.Office" / "FontCache"
    return sorted(base.glob("*/CloudFonts")) if base.is_dir() else []


def font_dirs() -> list[Path]:
    """Folders whose fonts count as 'installed on this computer' (PowerPoint for Mac also has its own)."""
    if os.environ.get("SLIDETISTIC_FONT_DIR"):
        return [Path(os.environ["SLIDETISTIC_FONT_DIR"])]
    cc = [creative_cloud_dir()] + office_cloud_dirs()
    if sys.platform == "win32":
        return [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts", install_dir()] + cc
    return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), install_dir(),
            Path("/Applications/Microsoft PowerPoint.app/Contents/Resources/DFonts")] + cc


def _names(path: Path) -> list[dict]:
    from fontTools.ttLib import TTCollection, TTFont
    try:
        fonts = TTCollection(str(path), lazy=True).fonts if path.suffix.lower() == ".ttc" else [TTFont(str(path), lazy=True)]
    except Exception:  # noqa: BLE001 — unreadable files simply don't count
        return []
    out = []
    for f in fonts:
        try:
            n = f["name"]
            out.append({"family": n.getDebugName(16) or n.getDebugName(1), "legacy": n.getDebugName(1),
                        "ps": n.getDebugName(6)})
        except Exception:  # noqa: BLE001
            continue
    return out


def installed() -> dict:
    """{'families': casefolded family names (typographic + legacy), 'ps': PostScript names, 'creative_cloud':
    the families that come from Creative Cloud (Adobe Fonts)}.
    Read with fontTools; cached by file path, size and modified time (a first scan of ~1,000 fonts takes a few
    seconds, later ones are instant)."""
    cache_path = fonts_catalog.cache_dir() / "installed-index.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    fresh, families, ps, adobe = {}, set(), set(), set()
    cc = creative_cloud_dir()
    for d in font_dirs():
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            try:
                st = p.stat()
            except OSError:             # a broken link (font removed, link left behind)
                continue
            key = f"{p}|{st.st_size}|{int(st.st_mtime)}"
            names = cache.get(key)
            if names is None:
                names = _names(p)
            fresh[key] = names
            for n in names:
                for k in ("family", "legacy"):
                    if n.get(k):
                        families.add(n[k].casefold())
                        if cc is not None and d == cc:
                            adobe.add(n[k].casefold())
                if n.get("ps"):
                    ps.add(n["ps"])
    if fresh != cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(fresh), encoding="utf-8")
    return {"families": families, "ps": ps, "creative_cloud": adobe}


# --- what a deck needs -------------------------------------------------------------------------------

def weight_of(suffix: str | None) -> int:
    return WEIGHTS.get((suffix or "regular").replace(" ", "").replace("-", "").casefold(), 400)


def variants_for(refs, base_weight: int) -> list[tuple[int, str]]:
    """(weight, 'normal'|'italic') pairs the deck's runs use: b/i flags on top of the family's own weight."""
    out = set()
    for r in refs:
        rp = r.run_props
        bold = rp is not None and rp.get("b") in ("1", "true")
        italic = rp is not None and rp.get("i") in ("1", "true")
        out.add((700 if bold and base_weight < 700 else base_weight, "italic" if italic else "normal"))
    return sorted(out) or [(base_weight, "normal")]


# --- download + check ---------------------------------------------------------------------------------

def _google_files(family: str, variants: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    spec = ";".join(f"{1 if st == 'italic' else 0},{w}" for w, st in sorted(variants, key=lambda v: (v[1] == "italic", v[0])))
    url = f"https://fonts.googleapis.com/css2?family={family.replace(' ', '+')}:ital,wght@{spec}"
    css = http.get(url, user_agent=LEGACY_UA).decode("utf-8", "replace")
    out = []
    for block in css.split("@font-face")[1:]:
        w = re.search(r"font-weight:\s*(\d+)", block)
        st = re.search(r"font-style:\s*(\w+)", block)
        src = re.search(r"url\((https://[^)]+\.ttf)\)", block)
        if w and st and src:
            out.append((int(w.group(1)), st.group(1), src.group(1)))
    return out


def _fontsource_files(entry: dict, variants: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    ver = fonts_catalog.details(entry["id"]).get("npmVersion") or "latest"
    return [(w, st, f"https://cdn.jsdelivr.net/fontsource/fonts/{entry['id']}@{ver}/latin-{w}-{st}.ttf")
            for w, st in variants if w in (entry.get("weights") or []) and st in (entry.get("styles") or [])]


PUBLISHER_MAX_BYTES = 200 * 1024 * 1024


def _publisher_files(entry: dict, p: dict) -> list[dict]:
    """A maker's archive (Microsoft's Aptos ZIP): downloaded once into the cache, then for each variant the file
    whose own name is the deck's family, preferring an exact legacy name ("Aptos Display" → Aptos-Display.ttf,
    though its typographic family is plain "Aptos")."""
    import hashlib
    import zipfile
    from fontTools.ttLib import TTFont
    cache = fonts_catalog.cache_dir() / "downloads" / (hashlib.sha1(entry["url"].encode()).hexdigest()[:12] + ".zip")
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        data = http.get(entry["url"], timeout=120, max_bytes=PUBLISHER_MAX_BYTES)
        want = entry.get("sha256")
        if want and hashlib.sha256(data).hexdigest() != want:
            # Pinned (review 2026-10-13): a changed file from the maker is checked by a person before use.
            raise RuntimeError(f"{entry.get('publisher', 'The')} download changed since SlideTistic last checked it; "
                               f"get it from {entry.get('page') or entry['url']}")
        cache.write_bytes(data)
    with zipfile.ZipFile(cache) as z:
        blobs = [z.read(n) for n in z.namelist() if n.lower().endswith((".ttf", ".otf"))]
    out = []
    for w, st in p["variants"]:
        best = None
        for data in blobs:
            if check_file(data, entry["family"], w, st) is None:
                exact = (TTFont(io.BytesIO(data), lazy=True)["name"].getDebugName(1) or "").casefold() == entry["family"].casefold()
                if best is None or exact > best[0]:
                    best = (exact, data)
        out.append({"weight": w, "style": st, "data": best[1] if best else None,
                    "problem": None if best else "not in the download"})
    return out


def check_file(data: bytes, family: str, weight: int, style: str) -> str | None:
    """None when the file is the font asked for, else why not. PowerPoint finds fonts by these names."""
    from fontTools.ttLib import TTFont
    try:
        f = TTFont(io.BytesIO(data))
        n = f["name"]
        typo, legacy = n.getDebugName(16) or n.getDebugName(1), n.getDebugName(1)
        cls = f["OS/2"].usWeightClass
        italic = bool(f["OS/2"].fsSelection & 1) or bool(f["head"].macStyle & 2)
    except Exception as e:  # noqa: BLE001
        return f"not a readable font ({type(e).__name__})"
    if "fvar" in f:
        return "variable font (PowerPoint needs a static file)"
    # Exact family, or the Windows-style "Family Weight" (Poppins SemiBold) whose weight word is the one asked
    # for. "Montserrat Thin" on a 400 file is Fontsource's misnaming and must be refused.
    legacy_rest = (legacy or "")[len(family):].strip() if (legacy or "").casefold().startswith(family.casefold()) else None
    named_ok = (typo or "").casefold() == family.casefold() or (
        legacy_rest is not None and (legacy_rest == "" or weight_of(legacy_rest) == weight
                                     and legacy_rest.replace(" ", "").casefold() in WEIGHTS))
    if not named_ok:
        return f"file is named '{typo}', not '{family}'"
    if cls != weight:
        return f"file is weight {cls}, not {weight}"
    if italic != (style == "italic"):
        return f"file is {'italic' if italic else 'upright'}, not {style}"
    return None


def plan(family: str, variants: list[tuple[int, str]]) -> dict:
    """What `get` would fetch: catalog entry, license, and variants the family has / lacks. No downloads."""
    entry = fonts_catalog.lookup(family)
    if entry is None:
        raise FontError(f"{family} isn't in the free-font catalog")
    have = [(w, st) for w, st in variants if w in (entry.get("weights") or []) and st in (entry.get("styles") or [])]
    return {"family": entry["family"], "id": entry["id"], "type": entry.get("type"), "source": entry.get("source"),
            "publisher": entry.get("publisher"), "license": entry.get("license"), "variants": have,
            "unavailable": [v for v in variants if v not in have]}


def download(family: str, variants: list[tuple[int, str]]) -> list[dict]:
    """Fetch and check each variant. Returns [{weight, style, data | None, problem | None}]."""
    p = plan(family, variants)
    entry = fonts_catalog.lookup(family)
    if p["type"] == "publisher":
        return _publisher_files(entry, p)
    files = _google_files(p["family"], p["variants"]) if p["type"] == "google" else _fontsource_files(entry, p["variants"])
    got = {(w, st): url for w, st, url in files}
    out = []
    for w, st in p["variants"]:
        url = got.get((w, st))
        if not url:
            out.append({"weight": w, "style": st, "data": None, "problem": "not offered by the font service"})
            continue
        data = http.get(url)
        problem = check_file(data, p["family"], w, st)
        out.append({"weight": w, "style": st, "data": None if problem else data, "problem": problem})
    return out


# --- install / uninstall ---------------------------------------------------------------------------

def _log_path() -> Path:
    return fonts_catalog.cache_dir() / "installed.json"


def _log() -> list[dict]:
    try:
        return json.loads(_log_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def install(family: str, files: list[dict], deck: str = "") -> list[dict]:
    """Install checked files for this user. Skips a font whose PostScript name is already installed
    (duplicate PostScript names confuse PowerPoint for Mac). Returns what happened per file."""
    from fontTools.ttLib import TTFont
    target = install_dir()
    target.mkdir(parents=True, exist_ok=True)
    have = installed()["ps"]
    log, results = _log(), []
    entry = fonts_catalog.lookup(family) or {"id": family.casefold().replace(" ", "-")}
    for f in files:
        if f.get("data") is None:
            results.append({**_strip(f), "installed": False})
            continue
        font = TTFont(io.BytesIO(f["data"]))
        ps, full = font["name"].getDebugName(6), font["name"].getDebugName(4)
        if ps in have:
            results.append({**_strip(f), "installed": False, "problem": "already installed"})
            continue
        path = target / f"SlideTistic-{entry['id']}-{f['weight']}{'i' if f['style'] == 'italic' else ''}.ttf"
        path.write_bytes(f["data"])
        if sys.platform == "win32" and not os.environ.get("SLIDETISTIC_FONT_DIR"):
            _windows_register(path, full)
        log.append({"family": family, "file": str(path), "ps": ps, "full": full, "deck": deck,
                    "t": time.strftime("%Y-%m-%dT%H:%M:%S")})
        results.append({**_strip(f), "installed": True, "file": str(path)})
    _log_path().parent.mkdir(parents=True, exist_ok=True)
    _log_path().write_text(json.dumps(log, indent=1), encoding="utf-8")
    return results


def uninstall(family: str | None = None) -> list[str]:
    """Remove fonts SlideTistic installed (all, or one family). Returns the files removed."""
    keep, removed = [], []
    for e in _log():
        if family is None or e["family"].casefold() == family.casefold():
            Path(e["file"]).unlink(missing_ok=True)
            if sys.platform == "win32" and not os.environ.get("SLIDETISTIC_FONT_DIR"):
                _windows_unregister(Path(e["file"]), e.get("full"))
            removed.append(e["file"])
        else:
            keep.append(e)
    _log_path().write_text(json.dumps(keep, indent=1), encoding="utf-8")
    return removed


def _strip(f: dict) -> dict:
    return {k: v for k, v in f.items() if k != "data"}


_REG = r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"


def _windows_register(path: Path, full_name: str) -> None:
    import ctypes
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG) as key:
        winreg.SetValueEx(key, f"{full_name} (TrueType)", 0, winreg.REG_SZ, str(path))
    ctypes.windll.gdi32.AddFontResourceW(str(path))
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)   # WM_FONTCHANGE


def _windows_unregister(path: Path, full_name: str | None) -> None:
    import ctypes
    import winreg
    ctypes.windll.gdi32.RemoveFontResourceW(str(path))
    if full_name:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, f"{full_name} (TrueType)")
        except OSError:
            pass
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 0x0002, 1000, None)


# --- collect: the deck's fonts in a folder next to it (David 2026-10-12, testing aid) --------------------

# Short weight words in commercial fonts' Windows names ("Proxima Nova Rg", "Museo Sans Bd").
ABBREV = {"th": 100, "lt": 300, "rg": 400, "md": 500, "sb": 600, "bd": 700, "xb": 800, "bk": 900, "blk": 900}

STYLE_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
               700: "Bold", 800: "ExtraBold", 900: "Black"}


def style_name(weight: int, style: str) -> str:
    base = STYLE_NAMES.get(weight, str(weight))
    if style == "italic":
        return "Italic" if base == "Regular" else f"{base} Italic"
    return base


def files_for(family: str, variants: list[tuple[int, str]]) -> dict:
    """Installed font files (Creative Cloud included) answering to `family`, one per variant when found.
    Returns {(weight, style): (path, from_creative_cloud)}."""
    installed()                                    # refreshes the index
    try:
        index = json.loads((fonts_catalog.cache_dir() / "installed-index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cc = creative_cloud_dir()
    want = family.casefold()
    paths = [key.rsplit("|", 2)[0] for key, names in index.items()
             if any((n.get("family") or "").casefold() == want or (n.get("legacy") or "").casefold().startswith(want)
                    for n in names)]
    out = {}
    variable = []
    for p in paths:
        if p.lower().endswith((".ttf", ".otf")):
            try:
                from fontTools.ttLib import TTFont
                if "fvar" in TTFont(p, lazy=True):
                    variable.append(p)
            except Exception:  # noqa: BLE001
                pass
    for w, st in variants:
        best = None
        for p in paths:
            if p.lower().endswith(".ttc"):
                continue                           # collections hold many fonts; linking one file is misleading
            try:
                data = Path(p).read_bytes()
            except OSError:
                continue
            if check_file(data, family, w, st) is None:
                from fontTools.ttLib import TTFont
                exact = (TTFont(io.BytesIO(data), lazy=True)["name"].getDebugName(1) or "").casefold() == want
                if best is None or exact > best[0]:
                    best = (exact, p)
        if best:
            out[(w, st)] = (best[1], cc is not None and Path(best[1]).parent == cc)
        elif variable:
            # A variable font holds every weight: one link stands for all of them (Source Sans 3 on this Mac).
            italic = [v for v in variable if "italic" in Path(v).name.lower()]
            pick = (italic or variable)[0] if st == "italic" else next((v for v in variable if v not in italic), variable[0])
            out[(w, st)] = (pick, cc is not None and Path(pick).parent == cc, "variable")
    return out


def safe_filename(name: str) -> str:
    """A font name from a deck as a file name: no folder separators, reserved characters or leading dots, so a
    crafted name ("../../x") can't write outside the fonts folder."""
    import re
    clean = re.sub(r'[\x00-\x1f/\\:*?"<>|]', "_", name).strip().lstrip(".")
    return clean[:200] or "font"


def collect(deck_path, out_dir=None, emit=lambda ev: None) -> dict:
    """Every non-Office font the deck's shown text uses, copied into '<deck> - fonts/' next to the deck and named by
    what it is ('Proxima Nova Bold.otf', not Creative Cloud's '.139.otf'). David 2026-10-12: a testing aid for his
    show content folders on his own machine. Installed and Creative Cloud fonts are copied from where they are;
    free fonts not on this computer (Microsoft / Fontsource / Google) are downloaded and checked. FONTS.txt lists
    every font, where it came from, and what couldn't be found."""
    from . import Deck, fonts, rules
    from .font_use import visible_fonts
    deck_path = Path(deck_path)
    deck = Deck(deck_path)
    folder = Path(out_dir) if out_dir else deck_path.parent / f"{deck_path.stem} - fonts"
    folder.mkdir(parents=True, exist_ok=True)
    office = rules.names("office_fonts") | rules.names("office_bundled_fonts")
    refs: dict[str, list] = {}
    for r in fonts.font_refs(deck):
        refs.setdefault(fonts.normalized_family(r.typeface), []).append(r)
    drawn = {}
    for v in visible_fonts(deck).values():
        fam = fonts.normalized_family(v["family"])
        drawn[fam.casefold()] = fam
    report = []
    for key, fam in sorted(drawn.items()):
        if key in office:
            continue
        suffix = fonts.flag_only_suffix(fam)
        base, weight = (fam[: -len(suffix)].strip(), weight_of(suffix)) if suffix else (fam, 400)
        word = fam.rsplit(" ", 1)
        if not suffix and len(word) == 2 and word[1].casefold() in ABBREV:   # "Proxima Nova Rg"
            base, weight = word[0], ABBREV[word[1].casefold()]
        variants = variants_for(refs.get(fam, []), weight) if refs.get(fam) else [(weight, "normal")]
        emit({"type": "progress", "family": fam, "message": f"Collecting {fam}…"})
        have = files_for(fam, variants) or files_for(base, variants)
        for w, st in variants:
            name = f"{base} {style_name(w, st)}"
            if (w, st) in have:
                src, from_cc, *kind = have[(w, st)]
                if kind:                            # variable font: one link per file, not per weight
                    name = f"{base}{' Italic' if 'italic' in Path(src).name.lower() else ''} (variable)"
                dest = folder / safe_filename(f"{name}{Path(src).suffix.lower() or '.otf'}")
                if dest.is_symlink() or dest.exists():
                    dest.unlink()
                shutil.copyfile(src, dest)
                if not any(r[0] == name for r in report):
                    from_office = any(Path(src).is_relative_to(d) for d in office_cloud_dirs())
                    report.append((name, "Creative Cloud" if from_cc else
                                   "Microsoft 365 cloud font (Office's download)" if from_office else "installed", src))
                continue
            entry = fonts_catalog.lookup(fam) or fonts_catalog.lookup(base)
            if entry is None:
                report.append((name, "not found", "not installed here and not a free download"))
                continue
            try:
                [got] = download(entry["family"], [(w, st)])
            except Exception as e:  # noqa: BLE001 — network boundary
                report.append((name, "download failed", str(e)))
                continue
            if got["data"] is None:
                report.append((name, "not available", got["problem"]))
                continue
            dest = folder / safe_filename(f"{name}.ttf")
            dest.write_bytes(got["data"])
            report.append((name, f"downloaded ({entry.get('publisher') or entry.get('source')})", str(dest)))
    lines = [f"Fonts for {deck_path.name} (collected {time.strftime('%Y-%m-%d %H:%M')} by SlideTistic)", ""]
    lines += [f"{n:<40} {how:<28} {where}" for n, how, where in report]
    (folder / "FONTS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"folder": str(folder), "fonts": [{"name": n, "how": h, "where": w} for n, h, w in report]}
