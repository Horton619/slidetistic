"""Shared font helpers for the F checks: where typefaces are used, what's embedded, name rules.

Ported from reference/fix_canva_fonts.py.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass

from fontTools.ttLib import TTFont
from pptx.oxml.ns import qn

from . import rules

TYPEFACE_TAGS = tuple(qn(t) for t in ("a:latin", "a:ea", "a:cs", "a:sym", "a:buFont"))
RUN_PROPS = {qn(t) for t in ("a:rPr", "a:defRPr", "a:endParaRPr")}
SLOTS = ("regular", "bold", "italic", "boldItalic")

EOT_COMPRESSED = 0x4          # MicroType Express: font data can't be read without a decompressor
EOT_XOR = 0x10000000          # font data XOR-obfuscated with 0x50
FSTYPE_RESTRICTED = 0x0002    # "Restricted License embedding": must not be embedded


# --- where fonts are used --------------------------------------------------------------------

@dataclass
class FontRef:
    part: object
    element: object               # a:latin / a:ea / a:cs / a:sym / a:buFont
    typeface: str
    slide: int | None             # set when the reference is on a slide

    @property
    def run_props(self):
        """The a:rPr-like parent that carries b/i flags, or None (theme fonts, bullet fonts)."""
        parent = self.element.getparent()
        return parent if parent is not None and parent.tag in RUN_PROPS else None


def font_refs(deck) -> list[FontRef]:
    """Every explicit typeface in the deck. Theme placeholders like '+mn-lt' are skipped."""
    refs = []
    slide_no = {id(s.part): i + 1 for i, s in enumerate(deck.slides)}
    for part, root in deck.xml_parts():
        for el in root.iter(*TYPEFACE_TAGS):
            tf = el.get("typeface")
            if tf and not tf.startswith("+"):
                refs.append(FontRef(part, el, tf, slide_no.get(id(part))))
    return refs


def usage_evidence(refs: list[FontRef]) -> dict:
    slides = sorted({r.slide for r in refs if r.slide})
    return {"uses": len(refs), "slides": slides}


def where(refs: list[FontRef]) -> str:
    slides = sorted({r.slide for r in refs if r.slide})
    if not slides:
        return "in masters/layouts only"
    return f"on {len(slides)} slide{'s' * (len(slides) != 1)}"


# --- name rules (rules/*.yaml) ---------------------------------------------------------------

def alias(name: str) -> str:
    return rules.load("font_aliases").get(name, name)


def split_style(name: str) -> tuple[str, bool, bool] | None:
    """'Roboto Bold Italic' → ('Roboto', True, True). None when no fixable suffix.

    'Tilda Sans Extra Bold' is NOT 'Tilda Sans Extra' + bold (Dropbox corpus 2026-10-09): a weight
    modifier before Bold makes it a weight PowerPoint can't switch to (F003's job).
    Repeated style words are all stripped: 'Barlow Bold Bold' → ('Barlow', True, False) (AACS corpus,
    2026-10-10: one word per pass took two repairs).
    """
    base, bold, italic = name, False, False
    while (step := _split_one_style(base)) is not None:
        base, b, i = step
        bold, italic = bold or b, italic or i
    return (base, bold, italic) if base != name else None


def _split_one_style(name: str) -> tuple[str, bool, bool] | None:
    modifiers = {m.casefold() for m in rules.load("weight_suffixes").get("modifiers", [])}
    for entry in rules.load("weight_suffixes")["fixable"]:
        suffix = " " + entry["suffix"]
        if name.endswith(suffix) and len(name) > len(suffix):
            base = name[: -len(suffix)]
            if base.rsplit(" ", 1)[-1].casefold() in modifiers:
                return None
            return base, entry.get("bold", False), entry.get("italic", False)
    return None


def flag_only_suffix(name: str) -> str | None:
    """'Montserrat SemiBold' → 'SemiBold'. These may be real installed family names."""
    for suffix in rules.load("weight_suffixes")["flag_only"]:
        if name.casefold().endswith(" " + suffix.casefold()):
            return suffix
    return None


def normalized_family(name: str) -> str:
    """The family a typeface really means: suffix stripped, alias applied."""
    split = split_style(name)
    return alias(split[0] if split else name)


def uncovered(deck, ctx) -> dict[str, list[FontRef]]:
    """Families (normalized) used in the deck that aren't embedded, Office fonts, on the crew list or
    Canva-only (F004 reports those), with their references. F007 and F009 share this rule."""
    from collections import defaultdict
    covered = (rules.names("office_fonts") | rules.names("office_bundled_fonts") | embedded_families(deck) | ctx.crew_fonts
               | {k.casefold() for k in rules.load("canva_only_fonts")})
    by_family = defaultdict(list)
    for r in font_refs(deck):
        fam = normalized_family(r.typeface)
        if fam.casefold() not in covered and r.typeface.casefold() not in covered:
            by_family[fam].append(r)
    return by_family


def canva_weight_embed(ef, s) -> bool:
    """'Roboto Bold' (regular slot) holding Roboto bold, or 'Calibri (MS)' holding Calibri: the listed name is
    the real family plus a style word / alias that F001/F002 also fix in the text, so F005 can re-file it."""
    split = split_style(ef.typeface)
    style_ok = (split[1], split[2]) == (s.info.bold, s.info.italic) if split else s.info.slot == s.slot
    return normalized_family(ef.typeface) == alias(s.info.family) and style_ok


def is_office_font(name: str) -> bool:
    return name.casefold() in rules.names("office_fonts")


# --- embedded fonts --------------------------------------------------------------------------

@dataclass
class EmbedInfo:
    family: str
    style: str
    bold: bool
    italic: bool
    compressed: bool
    fs_type: int

    @property
    def slot(self) -> str:
        return {(False, False): "regular", (True, False): "bold",
                (False, True): "italic", (True, True): "boldItalic"}[(self.bold, self.italic)]


@dataclass
class EmbeddedSlot:
    slot: str
    r_id: str
    info: EmbedInfo | None        # None when the font data can't be read at all


@dataclass
class EmbeddedFont:
    element: object               # p:embeddedFont
    typeface: str                 # the name the deck declares
    slots: list[EmbeddedSlot]


def embedded_font_list(deck):
    return deck.prs.part._element.find(qn("p:embeddedFontLst"))


def embedded_fonts(deck) -> list[EmbeddedFont]:
    lst = embedded_font_list(deck)
    if lst is None:
        return []
    out = []
    for ef in lst.findall(qn("p:embeddedFont")):
        font_el = ef.find(qn("p:font"))
        slots = []
        for slot in SLOTS:
            el = ef.find(qn(f"p:{slot}"))
            if el is None:
                continue
            r_id = el.get(qn("r:id"))
            try:
                blob = deck.prs.part.related_part(r_id).blob
            except KeyError:
                blob = None
            slots.append(EmbeddedSlot(slot, r_id, read_embed(blob) if blob else None))
        out.append(EmbeddedFont(ef, font_el.get("typeface") if font_el is not None else "", slots))
    return out


def embedded_families(deck) -> set[str]:
    """Casefolded families the deck carries, by declared name and by the name inside the file."""
    fams = set()
    for ef in embedded_fonts(deck):
        fams.add(normalized_family(ef.typeface).casefold())
        fams.update(alias(s.info.family).casefold() for s in ef.slots if s.info)
    return fams


def read_embed(data: bytes) -> EmbedInfo | None:
    """Family/style/flags of an embedded .fntdata blob (EOT, or a bare TTF/OTF)."""
    try:
        if data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            return _from_ttf(data, compressed=False)
        _eot_size, font_size, _ver, flags = struct.unpack_from("<IIII", data, 0)
        italic = bool(data[27])
        weight, = struct.unpack_from("<I", data, 28)
        fs_type, = struct.unpack_from("<H", data, 32)
        compressed = bool(flags & EOT_COMPRESSED)
        if not compressed:
            ttf = data[len(data) - font_size:]
            if flags & EOT_XOR:
                ttf = bytes(b ^ 0x50 for b in ttf)
            info = _from_ttf(ttf, compressed=False)
            if info:
                info.fs_type = fs_type
                return info
        family, style = _eot_names(data)
        return EmbedInfo(family, style, weight >= 600 or "bold" in style.lower(),
                         italic or "italic" in style.lower(), compressed, fs_type)
    except (struct.error, UnicodeDecodeError, IndexError):
        return None


def _from_ttf(ttf: bytes, compressed: bool) -> EmbedInfo | None:
    try:
        t = TTFont(io.BytesIO(ttf), lazy=True)
        n = t["name"]
        family = n.getDebugName(16) or n.getDebugName(1)
        style = n.getDebugName(17) or n.getDebugName(2) or ""
        os2 = t["OS/2"]
        return EmbedInfo(family, style, "bold" in style.lower() or os2.usWeightClass >= 600,
                         "italic" in style.lower(), compressed, os2.fsType)
    except Exception:  # noqa: BLE001 — any unreadable font is "unknown", never a crash
        return None


def _eot_names(data: bytes) -> tuple[str, str]:
    o, names = 82, []
    for _ in range(2):
        size, = struct.unpack_from("<H", data, o)
        o += 2
        names.append(data[o:o + size].decode("utf-16le").strip("\x00"))
        o += size + 2
    return names[0], names[1]
