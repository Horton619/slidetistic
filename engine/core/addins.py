"""Slides an add-in owns (rules/addin_slides.yaml): their findings are information only, never fixed."""
from __future__ import annotations

from dataclasses import replace

from pptx.oxml.ns import qn

from . import rules

TAGS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/tags"


def addin_slides(deck) -> dict[int, str]:
    """{slide number: add-in name} for slides carrying an add-in's tags (the slide's own or its shapes')."""
    memo = deck.__dict__.setdefault("_addin_slides", None)
    if memo is not None:
        return memo
    prefixes = [(p, name) for name, ps in (rules.load("addin_slides") or {}).items() for p in ps]
    out = {}
    for n, slide in enumerate(deck.slides, 1):
        for rel in slide.part.rels.values():
            if rel.reltype != TAGS or rel.is_external:
                continue
            for tag in _tag_names(rel.target_part):
                hit = next((name for p, name in prefixes if tag.startswith(p)), None)
                if hit:
                    out[n] = hit
                    break
            if n in out:
                break
    deck.__dict__["_addin_slides"] = out
    return out


def _tag_names(part) -> list[str]:
    from lxml import etree
    try:
        root = etree.fromstring(part.blob)
    except etree.XMLSyntaxError:
        return []
    return [t.get("name", "") for t in root.iter(qn("p:tag"))]


def mark(deck, findings: list) -> list:
    """Findings on add-in slides become information: the add-in replaces what's saved there at show time."""
    owned = addin_slides(deck)
    if not owned:
        return findings
    out = []
    for f in findings:
        if f.slide in owned and not f.informational:
            f = replace(f, informational=True,
                        evidence={**(f.evidence or {}), "addin": owned[f.slide],
                                  "rule": f"slide belongs to the {owned[f.slide]} add-in (rules/addin_slides.yaml): "
                                          "left alone"})
        out.append(f)
    return out
