"""Is a missing font on Adobe Fonts? (David 2026-10-13, action banners.)

Adobe's public family endpoint needs no token: `/families/<slug>` gives an id, `/families/<id>` the name,
foundry, libraries and the font's page. Answers (yes or no) are cached for 30 days. Activation itself is
David's click on Adobe's page (Adobe's terms rule out automating it); the app only opens the page and
watches Creative Cloud's font folder.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
from pathlib import Path

from . import fonts_catalog, http

API = "https://typekit.com/api/v1/json/families"
MAX_AGE_S = 30 * 86400


def slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.casefold()).strip("-")


_STYLE_WORD = re.compile(r"\s+(\d{3}|thin|hairline|light|book|regular|roman|medium|semi ?bold|demi ?bold|bold|"
                         r"extra ?bold|heavy|black|ultra|italic|oblique|rg|lt|bd|md|blk|it)$", re.I)


def base_family(family: str) -> str:
    """'Museo Sans 500' → 'Museo Sans', 'Proxima Nova Rg Bold' → 'Proxima Nova': Adobe lists families."""
    prev, out = None, family.strip()
    while prev != out:
        prev, out = out, _STYLE_WORD.sub("", out)
    return out or family


def search_link(family: str) -> str:
    from urllib.parse import quote
    return f"https://fonts.adobe.com/search?query={quote(family)}"


def _cache_path():
    return fonts_catalog.cache_dir() / "adobe-fonts.json"


def _cache() -> dict:
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fetch(s: str) -> dict | None:
    try:
        first = json.loads(http.get(f"{API}/{s}", timeout=15))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    fid = (first.get("family") or {}).get("id")
    if not fid or not re.fullmatch(r"[a-z0-9]+", fid):
        return None
    fam = json.loads(http.get(f"{API}/{fid}", timeout=15)).get("family") or {}
    link = str(fam.get("web_link") or "").replace("http://", "https://", 1)
    if not link.startswith("https://fonts.adobe.com/"):
        link = f"https://fonts.adobe.com/fonts/{s}"
    return {"name": fam.get("name") or "", "foundry": (fam.get("foundry") or {}).get("name"),
            "libraries": [lib.get("id") for lib in fam.get("libraries") or []], "link": link}


def lookup(families: list[str]) -> dict[str, dict | None]:
    """family → {name, foundry, libraries, link} when Adobe Fonts has exactly that family, else None.
    A family the lookup couldn't reach (offline) is left out, so the app shows a search link instead."""
    cache, now, out, dirty = _cache(), time.time(), {}, False
    for fam in families:
        name = base_family(fam)
        s = slug(name)
        if not s:
            out[fam] = None
            continue
        hit = cache.get(s)
        if hit is None or now - hit.get("t", 0) > MAX_AGE_S:
            try:
                info = _fetch(s)
            except Exception:  # noqa: BLE001 — network boundary: unknown, not "no"
                continue
            hit = cache[s] = {"t": now, "info": info}
            dirty = True
        info = hit["info"]
        # Same name only: Adobe's slug for "Gotham" may be a different family than the deck's Gotham.
        out[fam] = info if info and info["name"].casefold() == name.casefold() else None
    if dirty:
        _cache_path().parent.mkdir(parents=True, exist_ok=True)
        _cache_path().write_text(json.dumps(cache), encoding="utf-8")
    return out


def entitlements_path() -> Path:
    """Creative Cloud's own list of the fonts this account has added (CoreSync), with each one's install state."""
    import os
    import sys
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Adobe/CoreSync/plugins/livetype/c/entitlements.xml"
    return Path.home() / "Library/Application Support/Adobe/CoreSync/plugins/livetype/.c/entitlements.xml"


def added() -> list[dict]:
    """[{family, slug, state}] for every font Creative Cloud lists. state "OS": installed for every app
    (PowerPoint can use it); "CC": only Adobe's own apps can use it (David 2026-10-15: Abadi MT Pro was added
    that way; its files are encrypted and macOS doesn't register them)."""
    import re
    try:
        text = entitlements_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for block in re.findall(r"<font>(.*?)</font>", text, re.S):
        def tag(name):
            m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, re.S)
            return (m.group(1).strip() if m else "")
        url = tag("familyURL")
        out.append({"family": tag("familyName"), "slug": url.rstrip("/").rsplit("/", 1)[-1] if url else "",
                    "state": tag("installState")})
    return out


def added_state(family: str, link: str | None = None) -> str | None:
    """How Creative Cloud added this family: "OS" (usable everywhere), "CC" (Adobe apps only), or None. Matched
    by the Adobe page it came from (`link`) or by name: Adobe's family name can differ from the deck's
    ("Abadi" → "Abadi MT Pro")."""
    want = {slug(base_family(family))}
    if link:
        want.add(link.rstrip("/").rsplit("/", 1)[-1])
    names = {family.casefold(), base_family(family).casefold()}
    states = {f["state"] for f in added() if f["slug"] in want or f["family"].casefold() in names}
    return "OS" if "OS" in states else "CC" if "CC" in states else None
