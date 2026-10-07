from pptx.oxml.ns import qn

from engine.core import Deck, Status, fonts, registry
from engine.core.runner import RunConfig, repair, scan

CHECKS = {c.id: c for c in registry.discover()}


def run_scan(path, *ids, crew=()):
    return scan(path, [CHECKS[i] for i in ids], RunConfig(checks=set(ids), crew_fonts=set(crew)))


def run_repair(path, *ids, fix=None, crew=()):
    fixes = set(ids) if fix is None else set(fix)
    return repair(path, [CHECKS[i] for i in ids], RunConfig(checks=set(ids), fixes=fixes, crew_fonts=set(crew)),
                  out_path=path.with_name("out.pptx"))


def statuses(result, check_id):
    return {f.subject: f.status for f in result.findings if f.check_id == check_id}


def slide_runs(path):
    """[(typeface, bold)] for every run on every slide."""
    out = []
    for slide in Deck(path).slides:
        for latin in slide.part._element.iter(qn("a:latin")):
            rpr = latin.getparent()
            out.append((latin.get("typeface"), rpr.get("b")))
    return sorted(out, key=str)


def embedded(path):
    """{declared typeface: [slots]} of the saved deck."""
    return {ef.typeface: [s.slot for s in ef.slots] for ef in fonts.embedded_fonts(Deck(path))}


def font_parts(path):
    return sorted(str(p.partname) for p in Deck(path).prs.part.package.iter_parts()
                  if str(p.partname).startswith("/ppt/fonts/"))


__all__ = ["Status", "run_scan", "run_repair", "statuses", "slide_runs", "embedded", "font_parts"]
