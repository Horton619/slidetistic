from collections import defaultdict

from engine.core import Check, Finding, Status
from engine.core import fonts, rules


class CanvaOnlyFont(Check):
    id = "F004"
    title = "Canva-only font"
    group = "fonts"
    description = "Fonts that only exist inside Canva. No other computer can show them."
    report_only = True
    sources = ["canva", "any"]

    def detect(self, deck, ctx):
        catalog = {k.casefold(): (k, v) for k, v in rules.load("canva_only_fonts").items()}
        by_family = defaultdict(list)
        for r in fonts.font_refs(deck):
            fam = fonts.normalized_family(r.typeface).casefold()
            if fam in catalog:
                by_family[fam].append(r)
        findings = []
        for fam, group in sorted(by_family.items()):
            name, substitute = catalog[fam]
            tip = f" Suggested swap: {substitute}." if substitute else " Ask the presenter for a version in a standard font."
            findings.append(Finding(self.id, Status.RED,
                f"{name} only exists inside Canva, so PowerPoint will swap in another font ({fonts.where(group)}).{tip}",
                subject=name, evidence={**fonts.usage_evidence(group), "substitute": substitute}))
        return findings
