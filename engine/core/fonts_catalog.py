"""The free-font catalog (F009). Sources, in the order a name is looked up (David 2026-10-12):
1. Fonts their makers publish as free downloads (rules/font_downloads.yaml: Microsoft's Aptos family).
2. Fontsource's `/v1/fonts` (~2,100 open-licensed families: Google Fonts + ~120 others), no key.
3. Google Fonts' own family list (fonts.google.com/metadata/fonts), for anything Fontsource doesn't have.
A deck's name is matched exactly (ignoring case) in each source in turn, so the entry used always carries the
deck's own name ("if they disagree on the name, use the one that matches the name in the ppt").
Lists are cached and refreshed weekly; detection only reads the cache, so a scan never waits on the network.
See docs/F009_FONTSOURCE_DESIGN.md §10 for why Google-family files come from Google, not Fontsource.
"""
from __future__ import annotations

import json
import os
import sys
import time
from functools import lru_cache
from pathlib import Path

from . import http

API = "https://api.fontsource.org/v1/fonts"
GOOGLE_LIST = "https://fonts.google.com/metadata/fonts"
MAX_AGE_S = 7 * 24 * 3600
KEEP = ("id", "family", "type", "weights", "styles", "category", "version", "lastModified")


def cache_dir() -> Path:
    if os.environ.get("SLIDETISTIC_FONT_CACHE"):
        return Path(os.environ["SLIDETISTIC_FONT_CACHE"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SlideTistic" / "Cache" / "fonts"
    return Path.home() / "Library" / "Caches" / "SlideTistic" / "fonts"


def _catalog_file() -> Path:
    return cache_dir() / "catalog.json"


def refresh(force: bool = False) -> dict:
    """Download the family list if the cache is missing or a week old. Returns {"families", "fetched"}."""
    path = _catalog_file()
    if path.exists() and not force and time.time() - path.stat().st_mtime < MAX_AGE_S:
        return status()
    fonts = json.loads(http.get(API))
    slim = [{k: f.get(k) for k in KEEP} for f in fonts if f.get("id") and f.get("family")]
    try:
        google = _google_list()
    except Exception:  # noqa: BLE001 — the second list is a bonus; Fontsource alone still works
        google = []
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps({"fetched": time.strftime("%Y-%m-%dT%H:%M:%S"), "fonts": slim, "google": google}),
                   encoding="utf-8")
    os.replace(tmp, path)
    _load.cache_clear()
    return status()


def _google_list() -> list[dict]:
    raw = http.get(GOOGLE_LIST).decode("utf-8")
    raw = raw[raw.index("{"):]                      # the response may start with an anti-JSON-hijacking prefix
    out = []
    for f in json.loads(raw).get("familyMetadataList", []):
        keys = list((f.get("fonts") or {}).keys())                 # "400", "700i", …
        weights = sorted({int(k.rstrip("i")) for k in keys if k.rstrip("i").isdigit()})
        styles = sorted({"italic" if k.endswith("i") else "normal" for k in keys})
        out.append({"id": f["family"].casefold().replace(" ", "-"), "family": f["family"], "type": "google",
                    "weights": weights, "styles": styles, "source": "google"})
    return out


def status() -> dict:
    data = _load()
    return {"families": len(data["by_name"]), "fetched": data["fetched"], "path": str(_catalog_file())}


@lru_cache(maxsize=1)
def _load() -> dict:
    path = _catalog_file()
    if not path.exists():
        return {"by_name": {}, "fetched": None}
    raw = json.loads(path.read_text(encoding="utf-8"))
    by_name = {f["family"].casefold(): {**f, "source": "google" if f.get("type") == "google" else "fontsource"}
               for f in raw.get("google", [])}
    by_name.update({f["family"].casefold(): {**f, "source": "fontsource"} for f in raw.get("fonts", [])})
    return {"by_name": by_name, "fetched": raw.get("fetched")}


def publisher_fonts() -> dict:
    """casefolded family → entry, from rules/font_downloads.yaml (no network needed to know about them)."""
    from . import rules
    out = {}
    for key, pkg in (rules.load("font_downloads") or {}).items():
        for fam, spec in (pkg.get("families") or {}).items():
            out[fam.casefold()] = {"id": f"{key}:{fam}", "family": fam, "type": "publisher", "source": key,
                                   "publisher": pkg.get("publisher"), "url": pkg["url"], "page": pkg.get("page"),
                                   "license": pkg.get("license"), "weights": spec.get("weights", [400]),
                                   "styles": spec.get("styles", ["normal"])}
    return out


def available() -> bool:
    return _load()["fetched"] is not None


def lookup(family: str) -> dict | None:
    """Exact family name, ignoring case, in source order: publishers, Fontsource, Google. No fuzzy matching."""
    key = family.casefold()
    return publisher_fonts().get(key) or _load()["by_name"].get(key)


def details(font_id: str) -> dict:
    """`/v1/fonts/{id}`: adds license and npmVersion. Cached per id."""
    path = cache_dir() / "details" / f"{font_id}.json"
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_S:
        return json.loads(path.read_text(encoding="utf-8"))
    data = json.loads(http.get(f"{API}/{font_id}"))
    data.pop("variants", None)          # big, and the file URLs aren't used (Google serves the files)
    data.pop("unicodeRange", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data
