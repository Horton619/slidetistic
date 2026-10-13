"""What a repair must never change (review 2026-10-13, 3.4). Fixes move, resize, refile fonts, re-time media and
compress pictures; none of them adds or removes a slide or a shape, or changes a word. Checked on the saved output
against the input; a broken promise is a tool_error in the report, not a silent bad deck."""
from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

_SLIDE = re.compile(r"ppt/slides/slide(\d+)\.xml")
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _facts(path: Path) -> dict:
    """slide part → (shape ids, word counts); media file names. Read straight from the zip: no python-pptx."""
    slides, media = {}, set()
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if _SLIDE.fullmatch(name):
                root = etree.fromstring(z.read(name))
                ids = sorted(int(e.get("id")) for e in root.iter(f"{_P}cNvPr") if (e.get("id") or "").isdigit())
                words = Counter(w for t in root.iter(f"{_A}t") for w in (t.text or "").split())
                slides[name] = (ids, words)
            elif name.startswith("ppt/media/"):
                media.add(name)
    return {"slides": slides, "media": media}


def broken(original: Path, repaired: Path) -> list[str]:
    """Plain descriptions of every promise the repaired deck breaks; empty when it keeps them all."""
    a, b = _facts(Path(original)), _facts(Path(repaired))
    out = []
    if set(a["slides"]) != set(b["slides"]):
        out.append(f"the deck had {len(a['slides'])} slides and now has {len(b['slides'])}")
    for name in sorted(set(a["slides"]) & set(b["slides"]), key=lambda n: int(_SLIDE.fullmatch(n).group(1))):
        n = int(_SLIDE.fullmatch(name).group(1))
        (ids_a, words_a), (ids_b, words_b) = a["slides"][name], b["slides"][name]
        if ids_a != ids_b:
            lost, added = sorted(set(ids_a) - set(ids_b)), sorted(set(ids_b) - set(ids_a))
            out.append(f"slide part {n}: shapes changed (lost {lost or 'none'}, added {added or 'none'})")
        if words_a != words_b:
            gone = list((words_a - words_b).elements())[:5]
            new = list((words_b - words_a).elements())[:5]
            out.append(f"slide part {n}: text changed (missing {gone or 'nothing'}, new {new or 'nothing'})")
    if a["media"] - b["media"]:
        out.append(f"media files dropped: {sorted(a['media'] - b['media'])[:5]}")
    return out
