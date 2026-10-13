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
        # Canva embeds each weight under its own name ("Roboto Bold" holds Roboto's Bold face). After F001 renames
        # the text, F005 refiles that file into the base family's bold slot, so PowerPoint still finds it. That
        # only works when F005 can refile every file in the entry (fonts.canva_weight_embed): Dealer Trust's
        # "Arial Nova Condensed Bold" file says family "Arial Nova", and its "Arial Nova Bold" entry holds a
        # second oddly named file, so the rename orphaned them and the text went regular (2026-10-12). Those
        # names are left alone: PowerPoint (Mac and Windows) uses the embedded file for the name as written.
        stuck = {ef.typeface.casefold(): ef for ef in fonts.embedded_fonts(deck) if any(s.info for s in ef.slots)}
        office = rules.names("office_fonts")

        findings = []
        for name, group in sorted(by_name.items()):
            base, bold, italic = fonts.split_style(name)
            flags = " and ".join(f for f, on in (("bold", bold), ("italic", italic)) if on)
            evidence = {**fonts.usage_evidence(group), "becomes": base, "flags": flags}
            fam = fonts.alias(base).casefold()
            source = ("an Office font" if fam in rules.names("office_fonts") else
                      "embedded in the deck" if fam in fonts.embedded_families(deck) else
                      "on the crew font list" if fam in ctx.crew_fonts else "used elsewhere in the deck")
            evidence["rule"] = (f"'{name}' ends in a style word; '{base}' is {source}, so it's a fake family name"
                                if fam in known else
                                f"'{name}' ends in a style word, but '{base}' isn't an Office font, embedded, on the "
                                f"crew list, or used plainly in the deck, so it may be a real family name")
            ef = stuck.get(name.casefold())
            refileable = ef is not None and all(fonts.canva_weight_embed(ef, s) for s in ef.slots if s.info)
            if ef is not None and not refileable and fonts.alias(base).casefold() not in office:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"'{name}' ends in a style word, but the deck embeds a font under exactly that name, so "
                    f"PowerPoint uses it as is. Left alone ({fonts.where(group)}).",
                    subject=name, evidence={**evidence, "note": True, "embedded_as_named": True,
                                            "rule": f"'{name}' is the declared name of an embedded font whose file says "
                                                    f"family '{next((s.info.family for s in ef.slots if s.info), '?')}', "
                                                    f"not '{base}': it can't be refiled, so renaming would orphan it"}))
            elif fonts.alias(base).casefold() in known:
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

