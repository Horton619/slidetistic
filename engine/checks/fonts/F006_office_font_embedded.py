from pptx.oxml.ns import qn

from engine.core import Check, Finding, Status
from engine.core import fonts


class OfficeFontEmbedded(Check):
    id = "F006"
    title = "Office font embedded"
    group = "fonts"
    description = "A copy of a font every show machine already has (like Calibri). The copy can override the real one on Mac."
    default_fix = True
    sources = ["canva", "google", "any"]
    runs_after = ["F005"]

    def detect(self, deck, ctx):
        by_family: dict[str, list] = {}
        for ef in fonts.embedded_fonts(deck):
            if fonts.is_office_font(_family(ef)):
                by_family.setdefault(_family(ef), []).append(ef)
        return [
            Finding(self.id, Status.YELLOW,
                    f"{fam} is embedded, but every show machine already has it from Office. "
                    f"Fix: remove the embedded copy so the real font is used.",
                    subject=fam, evidence={"listed_as": [ef.typeface for ef in group]})
            for fam, group in sorted(by_family.items())
        ]

    def fix(self, deck, finding, edits, ctx):
        lst = fonts.embedded_font_list(deck)
        entries = fonts.embedded_fonts(deck)
        targets = [ef for ef in entries if _family(ef) == finding.subject]
        still_used = {s.r_id for ef in entries if ef not in targets for s in ef.slots}
        for target in targets:
            edits.replace_element(deck.prs.part, target.element, None, prop="embedded font",
                                  before=f"{target.typeface}: {', '.join(s.slot for s in target.slots)}",
                                  after="removed")
            for s in target.slots:
                if s.r_id not in still_used:
                    edits.drop_rel(deck.prs.part, s.r_id, prop="embedded font file",
                                   before=f"{target.typeface} {s.slot}")
        if len(lst.findall(qn("p:embeddedFont"))) == 0:
            edits.replace_element(deck.prs.part, lst, None, prop="embedded font list",
                                  before="empty list", after="removed")


def _family(ef) -> str:
    readable = [s.info.family for s in ef.slots if s.info]
    return fonts.alias(readable[0]) if readable else fonts.normalized_family(ef.typeface)
