"""Slide advance settings (p:transition) and slide-show settings (presProps.xml showPr).

PowerPoint 2010+ writes <p:transition> twice inside mc:AlternateContent (a p14 Choice and a plain
Fallback; corpus 2026-10-09: 695 slides). Read and edit every copy so they never disagree.
"""
from __future__ import annotations

from pptx.oxml.ns import qn


def transitions(slide) -> list:
    return list(slide._element.iter(qn("p:transition")))


def advance_after_ms(slide) -> int | None:
    for t in transitions(slide):
        if t.get("advTm") is not None:
            return int(t.get("advTm"))
    return None


def click_advance_off(slide) -> bool:
    return any(t.get("advClick") == "0" for t in transitions(slide))


def show_settings(deck):
    """(presProps part, root, <p:showPr> or None)."""
    for part, root in deck.xml_parts():
        if str(part.partname) == "/ppt/presProps.xml":
            return part, root, root.find(qn("p:showPr"))
    return None, None, None


def uses_timings(deck) -> bool:
    _, _, show = show_settings(deck)
    return show is None or show.get("useTimings") != "0"


def animated_shape_ids(slide) -> set[int]:
    """Shape ids that appear or disappear by animation (entrance/exit effects), plus every shape
    inside an animated group: their text isn't on screen with everything else all the time.
    TSCRA CWD slide 41 (2026-10-11): 22 year cards stacked in one spot, each appearing on a click,
    read as 231 "text over text" collisions and kept a repair busy for 55 minutes."""
    timing = slide._element.find(qn("p:timing"))
    if timing is None:
        return set()
    ids = set()
    for ctn in timing.iter(qn("p:cTn")):
        if ctn.get("presetClass") in ("entr", "exit"):
            ids |= {int(t.get("spid")) for t in ctn.iter(qn("p:spTgt")) if (t.get("spid") or "").isdigit()}
    if not ids:
        return ids
    for grp in slide._element.iter(qn("p:grpSp")):
        nv = grp.find(qn("p:nvGrpSpPr"))
        c_nv = nv.find(qn("p:cNvPr")) if nv is not None else None
        if c_nv is not None and int(c_nv.get("id", -1)) in ids:
            ids |= {int(e.get("id")) for e in grp.iter(qn("p:cNvPr")) if (e.get("id") or "").isdigit()}
    return ids

