from collections import defaultdict

from engine.core import Check, Finding, FixRefused, Status
from engine.core import fonts, rules


class WeightInFamilyName(Check):
    id = "F001"
    title = "Weight in font name"
    group = "fonts"
    description = "Font names like 'Roboto Bold' that Mac PowerPoint can't find. Renamed to the real family with bold/italic on."
    default_fix = True
    sources = ["canva", "google", "any"]

    def detect(self, deck, ctx):
        refs = fonts.font_refs(deck)
        # Families we know exist: Office, embedded in this deck, on the show machines, or used
        # elsewhere in the deck without a style word.
        known = (rules.names("office_fonts") | fonts.embedded_families(deck) | ctx.crew_fonts
                 | {r.typeface.casefold() for r in refs if not fonts.split_style(r.typeface)})
        by_name = defaultdict(list)
        for r in refs:
            if fonts.split_style(r.typeface):
                by_name[r.typeface].append(r)

        findings = []
        for name, group in sorted(by_name.items()):
            base, bold, italic = fonts.split_style(name)
            flags = " and ".join(f for f, on in (("bold", bold), ("italic", italic)) if on)
            evidence = {**fonts.usage_evidence(group), "becomes": base, "flags": flags}
            if fonts.alias(base).casefold() in known:
                findings.append(Finding(self.id, Status.RED,
                    f"'{name}' isn't a real font name, so Mac PowerPoint swaps in another font "
                    f"({fonts.where(group)}). Fix: '{base}' with {flags} on.",
                    subject=name, evidence=evidence))
            else:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"'{name}' ends in a style word, but no '{base}' font is in this deck or on the show "
                    f"machines. It may be a real font name, so it was left alone ({fonts.where(group)}).",
                    subject=name, evidence=evidence))
        return findings

    def fix(self, deck, finding, edits, ctx):
        if finding.status != Status.RED:
            raise FixRefused(f"'{finding.subject}' may be a real font name")
        base, bold, italic = fonts.split_style(finding.subject)
        for ref in fonts.font_refs(deck):
            if ref.typeface != finding.subject:
                continue
            edits.set_part_attr(ref.part, ref.element, "typeface", base, prop="font name")
            rpr = ref.run_props
            if rpr is not None:
                if bold:
                    edits.set_part_attr(ref.part, rpr, "b", "1", prop="bold")
                if italic:
                    edits.set_part_attr(ref.part, rpr, "i", "1", prop="italic")

