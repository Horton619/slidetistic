from lxml import etree
from pptx.oxml.ns import qn

from engine.core import Check, Finding, Status
from engine.core import fonts


class EmbeddedFontListMismatch(Check):
    id = "F005"
    title = "Embedded fonts filed under wrong names"
    group = "fonts"
    description = "The deck's list of embedded fonts doesn't match the font files inside, so Mac can't use them."
    default_fix = True
    sources = ["canva", "google", "any"]

    def detect(self, deck, ctx):
        findings = []
        for ef in fonts.embedded_fonts(deck):
            wrong = [s for s in ef.slots if s.info and
                     (fonts.alias(s.info.family) != ef.typeface or s.info.slot != s.slot)]
            if not wrong:
                continue
            what = ", ".join(f"{fonts.alias(s.info.family)} {s.info.slot}" for s in wrong)
            findings.append(Finding(self.id, Status.RED,
                f"Embedded font listed as '{ef.typeface}' is really {what}. "
                f"Mac PowerPoint can't match it to the text. Fix: re-file it under its real name.",
                subject=ef.typeface, evidence={"slots": [
                    {"listed": s.slot, "family": s.info.family, "style": s.info.style} for s in wrong]}))
        return findings

    def fix(self, deck, finding, edits, ctx):
        # Rebuilding the whole list is idempotent: later findings in the same repair are no-ops.
        lst = fonts.embedded_font_list(deck)
        if lst is None:
            return
        new = _rebuilt(lst, fonts.embedded_fonts(deck))
        edits.replace_element(deck.prs.part, lst, new, prop="embedded font list",
                              before=_summary(fonts.embedded_fonts(deck)), after=_describe(new))


def _rebuilt(lst, entries):
    """Group font files by the family/style read from the files themselves. First file wins a slot."""
    families: dict[str, dict[str, str]] = {}
    for ef in entries:
        for s in ef.slots:
            fam, slot = (fonts.alias(s.info.family), s.info.slot) if s.info else (ef.typeface, s.slot)
            families.setdefault(fam, {}).setdefault(slot, s.r_id)
    new = etree.Element(lst.tag, nsmap=lst.nsmap)
    for fam, slots in families.items():
        ef = etree.SubElement(new, qn("p:embeddedFont"))
        etree.SubElement(ef, qn("p:font"), typeface=fam)
        for slot in fonts.SLOTS:
            if slot in slots:
                etree.SubElement(ef, qn(f"p:{slot}"), {qn("r:id"): slots[slot]})
    return new


def _summary(entries) -> str:
    return "; ".join(f"{ef.typeface}: {', '.join(s.slot for s in ef.slots)}" for ef in entries)


def _describe(lst) -> str:
    out = []
    for ef in lst.findall(qn("p:embeddedFont")):
        slots = [c.tag.split("}")[1] for c in ef if c.tag != qn("p:font")]
        out.append(f"{ef.find(qn('p:font')).get('typeface')}: {', '.join(slots)}")
    return "; ".join(out)
