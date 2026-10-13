from lxml import etree
from pptx.oxml.ns import qn

from engine.core import Check, Finding, FixRefused, Status
from engine.core import fonts


class EmbeddedFontListMismatch(Check):
    id = "F005"
    title = "Embedded fonts filed under wrong names"
    group = "fonts"
    description = "The deck's list of embedded fonts doesn't match the font files inside, so Mac can't use them."
    default_fix = True
    sources = ["canva", "google", "any"]
    # F001/F002 rename the text first; only then can an embed safely move to the real name.
    runs_after = ["F001", "F002"]

    def detect(self, deck, ctx):
        findings = []
        for ef in fonts.embedded_fonts(deck):
            wrong = [s for s in ef.slots if _misfiled(ef, s)]
            if not wrong:
                continue
            what = ", ".join(f"{fonts.alias(s.info.family)} {s.info.slot}" for s in wrong)
            evidence = {"slots": [{"listed": s.slot, "family": s.info.family, "style": s.info.style} for s in wrong]}
            evidence["rule"] = ("listed name = real family + a style word/alias that F001/F002 also fix in the text, "
                                "so it can be re-filed safely" if all(_canva_pattern(ef, s) for s in wrong) else
                                "the text uses the listed name; re-filing would disconnect it from its font")
            if all(_canva_pattern(ef, s) for s in wrong):
                findings.append(Finding(self.id, Status.RED,
                    f"Embedded font listed as '{ef.typeface}' is really {what}. "
                    f"Mac PowerPoint can't match it to the text. Fix: re-file it under its real name.",
                    subject=ef.typeface, evidence=evidence))
            elif {fonts.alias(s.info.family) for s in wrong} <= {"Arial", "Calibri", "Times New Roman"} \
                    and fonts.normalized_family(ef.typeface) not in {fonts.alias(s.info.family) for s in wrong}:
                stand_in = fonts.alias(wrong[0].info.family)
                findings.append(Finding(self.id, Status.YELLOW,
                    f"'{ef.typeface}' couldn't be embedded, so the exporter put {stand_in} in its place. "
                    f"Text in {ef.typeface} will show as {stand_in}; get the real font if the look matters.",
                    subject=ef.typeface, evidence={**evidence, "stand_in": stand_in}))
            else:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"Embedded font listed as '{ef.typeface}' contains {what}. The text uses the listed "
                    f"name, so it's left as is; check this font on a Mac.",
                    subject=ef.typeface, evidence=evidence))
        return findings

    def fix(self, deck, finding, edits, ctx):
        if finding.status != Status.RED:
            raise FixRefused("re-filing it would disconnect it from the text that uses it")
        # Rebuilding the whole list is idempotent: later findings in the same repair are no-ops.
        lst = fonts.embedded_font_list(deck)
        if lst is None:
            return
        used = {r.typeface for r in fonts.font_refs(deck)}
        entries = fonts.embedded_fonts(deck)
        if not any(_safe_to_move(ef, s, used) for ef in entries for s in ef.slots if _misfiled(ef, s)):
            raise FixRefused(f"text still uses '{finding.subject}'; turn on F001/F002 so the text is renamed first")
        new = _rebuilt(lst, entries, used)
        edits.replace_element(deck.prs.part, lst, new, prop="embedded font list",
                              before=_summary(fonts.embedded_fonts(deck)), after=_describe(new))


def _misfiled(ef, s) -> bool:
    return s.info is not None and (fonts.alias(s.info.family) != ef.typeface or s.info.slot != s.slot)


def _canva_pattern(ef, s) -> bool:
    return fonts.canva_weight_embed(ef, s)          # shared with F001, which renames only what F005 can re-file


def _safe_to_move(ef, s, used: set[str]) -> bool:
    # Never re-file under a new name while text still asks for the old one: on Windows the
    # embed would stop matching and a font that works today would be lost.
    return s.info is not None and _canva_pattern(ef, s) and ef.typeface not in used


def _rebuilt(lst, entries, used: set[str]):
    """Re-file safe slots by the family/style read from the files. First file wins a slot."""
    families: dict[str, dict[str, str]] = {}
    for ef in entries:
        for s in ef.slots:
            if _safe_to_move(ef, s, used):
                fam, slot = fonts.alias(s.info.family), s.info.slot
            else:
                fam, slot = ef.typeface, s.slot
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
