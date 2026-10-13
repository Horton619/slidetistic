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
        by_family = fonts.uncovered(deck, ctx)       # Canva-only fonts are left to F004
        mac_only = {k.casefold(): v for k, v in rules.load("mac_only_fonts").items()}
        cloud, windows = rules.names("conditional_fonts", "office_cloud"), rules.names("conditional_fonts", "windows")
        from engine.core.font_use import visible_fonts
        drawn = {fonts.normalized_family(v["family"]).casefold() for v in visible_fonts(deck).values()} if by_family else set()
        findings = []
        for fam, group in sorted(by_family.items()):
            if fam.casefold() not in drawn and not any(r.typeface.casefold() in drawn for r in group):
                # Named in a master, layout, theme or empty run, but no shown text uses it (David 2026-10-12;
                # 58 of 116 suite reds, checked against PowerPoint's PDFs). PowerPoint may still warn about it.
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} is named in the deck but no text on any slide uses it ({fonts.where(group)}). "
                    "PowerPoint may list it as missing; nothing on screen changes.",
                    subject=fam, evidence={**fonts.usage_evidence(group), "names": sorted({r.typeface for r in group}),
                                           "drawn": False, "note": True,
                                           "rule": "no run with text resolves to this font (slides, SmartArt, charts, "
                                                   "layout/master text; inheritance through placeholders and theme)"}))
                continue
            swap = mac_only.get(fam.casefold())
            if fam.casefold() in cloud:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} is a Microsoft 365 cloud font: current Office downloads it when online, but "
                    f"Office 2019/2021 or an offline machine won't have it ({fonts.where(group)}).",
                    subject=fam, evidence={**fonts.usage_evidence(group), "tier": "office_cloud", "rule": "family is in conditional_fonts.yaml office_cloud"}))
                continue
            if fam.casefold() in windows:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} comes with Windows: fine on a PC show machine, but it will look different "
                    f"when previewed on a Mac ({fonts.where(group)}).",
                    subject=fam, evidence={**fonts.usage_evidence(group), "tier": "windows", "rule": "family is in conditional_fonts.yaml windows"}))
                continue
            if swap:
                msg = (f"{fam} is a Mac system font, so Windows show machines won't have it "
                       f"({fonts.where(group)}). Suggested swap: {swap}.")
            else:
                msg = (f"{fam} isn't embedded and isn't an Office font. Unless it's installed on the show "
                       f"machine, PowerPoint swaps in another font ({fonts.where(group)}).")
            findings.append(Finding(self.id, Status.RED, msg, subject=fam,
                evidence={**fonts.usage_evidence(group), "names": sorted({r.typeface for r in group}),
                          "mac_only_swap": swap,
                          "rule": "not embedded, not in office_fonts.yaml / conditional_fonts.yaml, not on the crew list"}))
        return findings
