from collections import defaultdict

from engine.core import Check, Finding, Status
from engine.core import fonts, rules


class OtherWeightNames(Check):
    id = "F003"
    title = "Weight PowerPoint can't switch"
    group = "fonts"
    description = "Names like 'Montserrat SemiBold' where Montserrat is available but that weight needs its own installed font."
    report_only = True
    sources = ["canva", "google", "any"]

    def detect(self, deck, ctx):
        # Only when the base family is available: if it isn't, F007 already reports the font missing.
        available = rules.names("office_fonts") | fonts.embedded_families(deck) | ctx.crew_fonts
        by_name = defaultdict(list)
        for r in fonts.font_refs(deck):
            name, weight = r.typeface, fonts.flag_only_suffix(r.typeface)
            if not weight or name.casefold() in available:
                continue
            base = name[: -len(weight)].rstrip()
            if base.casefold() in available:
                by_name[name].append(r)
        findings = []
        for name, group in sorted(by_name.items()):
            weight = fonts.flag_only_suffix(name)
            base = name[: -len(weight)].rstrip()
            findings.append(Finding(self.id, Status.YELLOW,
                f"'{name}': {base} is available, but PowerPoint can only switch it to bold or italic. "
                f"{weight} shows only if a font named exactly '{name}' is installed on the show machine "
                f"({fonts.where(group)}).",
                subject=name, evidence={**fonts.usage_evidence(group), "weight": weight, "base": base}))
        return findings
