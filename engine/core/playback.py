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
