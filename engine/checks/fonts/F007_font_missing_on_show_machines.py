from collections import defaultdict

from engine.core import Check, Finding, Status
from engine.core import fonts, rules


class FontMissingOnShowMachines(Check):
    id = "F007"
    title = "Font may be missing on show machines"
    group = "fonts"
    description = "Fonts that aren't embedded, aren't Office fonts, and aren't in the crew's installed-font list."
    report_only = True
    sources = ["canva", "google", "any"]

    def detect(self, deck, ctx):
        covered = (rules.names("office_fonts") | fonts.embedded_families(deck) | ctx.crew_fonts
                   | {k.casefold() for k in rules.load("canva_only_fonts")})   # F004 reports those
        by_family = defaultdict(list)
        for r in fonts.font_refs(deck):
            fam = fonts.normalized_family(r.typeface)
            if fam.casefold() not in covered and r.typeface.casefold() not in covered:
                by_family[fam].append(r)
        return [
            Finding(self.id, Status.RED,
                    f"{fam} isn't embedded and isn't an Office font. Unless it's installed on the show "
                    f"machine, PowerPoint swaps in another font ({fonts.where(group)}).",
                    subject=fam, evidence={**fonts.usage_evidence(group), "names": sorted({r.typeface for r in group})})
            for fam, group in sorted(by_family.items())
        ]
