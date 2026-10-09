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
        mac_only = {k.casefold(): v for k, v in rules.load("mac_only_fonts").items()}
        cloud, windows = rules.names("conditional_fonts", "office_cloud"), rules.names("conditional_fonts", "windows")
        findings = []
        for fam, group in sorted(by_family.items()):
            swap = mac_only.get(fam.casefold())
            if fam.casefold() in cloud:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} is a Microsoft 365 cloud font: current Office downloads it when online, but "
                    f"Office 2019/2021 or an offline machine won't have it ({fonts.where(group)}).",
                    subject=fam, evidence={**fonts.usage_evidence(group), "tier": "office_cloud"}))
                continue
            if fam.casefold() in windows:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} comes with Windows: fine on a PC show machine, but it will look different "
                    f"when previewed on a Mac ({fonts.where(group)}).",
                    subject=fam, evidence={**fonts.usage_evidence(group), "tier": "windows"}))
                continue
            if swap:
                msg = (f"{fam} is a Mac system font, so Windows show machines won't have it "
                       f"({fonts.where(group)}). Suggested swap: {swap}.")
            else:
                msg = (f"{fam} isn't embedded and isn't an Office font. Unless it's installed on the show "
                       f"machine, PowerPoint swaps in another font ({fonts.where(group)}).")
            findings.append(Finding(self.id, Status.RED, msg, subject=fam,
                evidence={**fonts.usage_evidence(group), "names": sorted({r.typeface for r in group}),
                          "mac_only_swap": swap}))
        return findings
