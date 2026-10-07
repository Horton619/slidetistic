from collections import defaultdict

from engine.core import Check, Finding, Status
from engine.core import fonts, rules


class CanvaFontAlias(Check):
    id = "F002"
    title = "App-private font name"
    group = "fonts"
    description = "Private names like Canva's 'Calibri (MS)' that no computer has. Renamed to the real font."
    default_fix = True
    sources = ["canva", "any"]
    runs_after = ["F001"]

    def detect(self, deck, ctx):
        by_alias = defaultdict(list)
        for r in fonts.font_refs(deck):
            a = _alias_in(r.typeface)
            if a:
                by_alias[a].append(r)
        aliases = rules.load("font_aliases")
        return [
            Finding(self.id, Status.RED,
                    f"'{a}' is a private name for {aliases[a]}; no computer has a font called that "
                    f"({fonts.where(group)}). Fix: rename to {aliases[a]}.",
                    subject=a, evidence={**fonts.usage_evidence(group), "becomes": aliases[a],
                                         "names": sorted({r.typeface for r in group})})
            for a, group in sorted(by_alias.items())
        ]

    def fix(self, deck, finding, edits, ctx):
        a = finding.subject
        target = rules.load("font_aliases")[a]
        for ref in fonts.font_refs(deck):
            if _alias_in(ref.typeface) == a:
                # 'Calibri (MS) Bold' → 'Calibri Bold' when F001 is off; F001 normally strips it first.
                edits.set_part_attr(ref.part, ref.element, "typeface", target + ref.typeface[len(a):],
                                    prop="font name")


def _alias_in(typeface: str) -> str | None:
    aliases = rules.load("font_aliases")
    if typeface in aliases:
        return typeface
    split = fonts.split_style(typeface)
    return split[0] if split and split[0] in aliases else None
