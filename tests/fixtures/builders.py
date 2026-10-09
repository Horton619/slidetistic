"""Tiny decks built in code. Each helper returns a function that adds one shape to a shape tree.

    path = make_deck(tmp_path, text_box(x=-0.5, text="hi", font="Roboto Bold"))
    path = make_deck(tmp_path, slides=[[title("A")], [picture(x=-1)]], size=CANVA)
"""
from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

WIDE = (13.333, 7.5)        # PowerPoint 16:9
GOOGLE = (10, 5.625)
CANVA = (20, 11.25)
STANDARD = (10, 7.5)        # 4:3


def text_box(text="Text", x=1, y=1, w=4, h=1, font=None, size=None, rotation=0, name=None, bold=None,
             link=None):
    def add(shapes):
        tb = shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tb.text_frame.text = text
        run = tb.text_frame.paragraphs[0].runs[0]
        if font:
            run.font.name = font
        if size:
            run.font.size = Pt(size)
        if bold is not None:
            run.font.bold = bold
        if link:
            run.hyperlink.address = link
        if rotation:
            tb.rotation = rotation
        if name:
            tb.name = name
        return tb
    return add


def picture(x=1, y=1, w=2, h=2, px=(4, 4), link=None, blob=None):
    """`px` is the image's pixel size; `blob` overrides the image bytes entirely."""
    def add(shapes):
        pic = shapes.add_picture(io.BytesIO(blob or _png(*px)), Inches(x), Inches(y), Inches(w), Inches(h))
        if link:
            pic.click_action.hyperlink.address = link
        return pic
    return add


def group(*children, x=None, y=None):
    """A group of the given shapes. x/y (inches) move the whole group after building."""
    def add(shapes):
        grp = shapes.add_group_shape()
        for child in children:
            child(grp.shapes)
        if x is not None:
            grp.left = Inches(x)
        if y is not None:
            grp.top = Inches(y)
        return grp
    return add


def table(rows=2, cols=2, text="cell", x=1, y=1, w=4, h=1):
    def add(shapes):
        gf = shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(h))
        for row in gf.table.rows:
            for cell in row.cells:
                cell.text = text
        return gf
    return add


def embed(declared: str, slot: str, family: str, style: str = "Regular", *, weight=None,
          compressed=False, fs_type=0, bare_ttf=False):
    """An embedded font entry: listed as `declared`/`slot`, but the file inside is `family` `style`."""
    return dict(declared=declared, slot=slot, family=family, style=style,
                weight=weight or (700 if "Bold" in style else 400), italic="Italic" in style,
                compressed=compressed, fs_type=fs_type, bare_ttf=bare_ttf)


def make_deck(folder: Path, *shapes, slides=None, size=WIDE, notes=None, layout=6,
              titles=None, name="deck.pptx", embeds=(), hidden=(), post=None) -> Path:
    """`shapes` fills one slide; `slides` is a list of shape lists. layout 6 = Blank, 0/1 have placeholders.

    notes: one string for every slide, or a list per slide. hidden: 1-based slide numbers.
    post(prs): last-chance hook for parts the helpers don't cover (comments, macros, external rels).
    """
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(size[0]), Inches(size[1])
    for i, slide_shapes in enumerate(slides if slides is not None else [list(shapes)]):
        slide = prs.slides.add_slide(prs.slide_layouts[layout])
        for add in slide_shapes:
            add(slide.shapes)
        if titles and slide.shapes.title is not None:
            slide.shapes.title.text = titles[i]
        slide_notes = notes[i] if isinstance(notes, list) else notes
        if slide_notes:
            slide.notes_slide.notes_text_frame.text = slide_notes
        if i + 1 in hidden:
            slide._element.set("show", "0")
    if embeds:
        _embed_fonts(prs, embeds)
    if post:
        post(prs)
    path = Path(folder) / name
    prs.save(str(path))
    return path


def _embed_fonts(prs, embeds):
    """Adds font parts + <p:embeddedFontLst> the way Canva/PowerPoint store them."""
    pres = prs.part._element
    lst = pres.makeelement(qn("p:embeddedFontLst"), {})
    pres.find(qn("p:notesSz")).addnext(lst)   # schema order: right after notesSz
    entries = {}
    for n, e in enumerate(embeds, 1):
        ttf = make_ttf(e["family"], e["style"], e["weight"], e["fs_type"])
        blob = ttf if e["bare_ttf"] else make_eot(ttf, e["family"], e["style"], e["weight"],
                                                    e["italic"], e["fs_type"], e["compressed"])
        part = Part(PackURI(f"/ppt/fonts/font{n}.fntdata"), "application/x-fontdata", prs.part.package, blob)
        r_id = prs.part.relate_to(part, RT.FONT)
        if e["declared"] not in entries:
            ef = lst.makeelement(qn("p:embeddedFont"), {})
            lst.append(ef)
            ef.append(ef.makeelement(qn("p:font"), {"typeface": e["declared"]}))
            entries[e["declared"]] = ef
        ef = entries[e["declared"]]
        ef.append(ef.makeelement(qn(f"p:{e['slot']}"), {qn("r:id"): r_id}))


def make_ttf(family: str, style: str = "Regular", weight: int = 400, fs_type: int = 0) -> bytes:
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({0x41: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((500, 0)); pen.lineTo((250, 700)); pen.closePath()
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": style})
    fb.setupOS2(usWeightClass=weight, fsType=fs_type)
    fb.setupPost()
    out = io.BytesIO()
    fb.save(out)
    return out.getvalue()


def make_eot(ttf: bytes, family: str, style: str, weight: int, italic: bool, fs_type: int,
             compressed: bool) -> bytes:
    """EOT v2.1 header + font data. `compressed` sets the MTX flag with junk data (unreadable, like real MTX)."""
    data = b"\x00" * 64 if compressed else ttf
    flags = 0x4 if compressed else 0

    def name(s):
        b = s.encode("utf-16le")
        return struct.pack("<H", len(b)) + b

    names = (name(family) + b"\0\0" + name(style) + b"\0\0" + name("Version 1.0") + b"\0\0"
             + name(f"{family} {style}") + b"\0\0" + name(""))
    fixed = (struct.pack("<III", len(data), 0x00020001, flags) + b"\0" * 10 + bytes([1, int(italic)])
             + struct.pack("<IHH", weight, fs_type, 0x504C) + b"\0" * 44 + b"\0\0")
    body = fixed + names
    total = 4 + len(body) + len(data)
    return struct.pack("<I", total) + body + data


def add_part(prs, source_part, partname: str, content_type: str, reltype: str, blob: bytes = b"x"):
    """Attach a bare part (comments, vbaProject, activeX…) to `source_part`."""
    part = Part(PackURI(partname), content_type, prs.part.package, blob)
    return source_part.relate_to(part, reltype)


def _png(w=4, h=4) -> bytes:
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * w for _ in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# The decks every check must survive without crashing (SPEC §8, contract tests).
CORNER_DECKS = {
    "empty": lambda d: make_deck(d, slides=[]),
    "blank_slide": lambda d: make_deck(d),
    "all_pictures": lambda d: make_deck(d, picture(), picture(x=-1), picture(x=12, w=3)),
    "groups": lambda d: make_deck(d, group(text_box("in group"), picture())),
    "nested_groups": lambda d: make_deck(d, group(group(text_box("deep", x=-0.5)), text_box("mid"), x=2)),
    "rotated": lambda d: make_deck(d, text_box("tilted", rotation=30), text_box("upside", rotation=180)),
    "table": lambda d: make_deck(d, table()),
    "placeholders": lambda d: make_deck(d, layout=1, titles=["Title placeholder"]),
    "notes_only_text": lambda d: make_deck(d, picture(), notes="Speaker notes only"),
    "non_latin": lambda d: make_deck(d, text_box("日本語のテキスト"), text_box("مرحبا"), text_box("Ελληνικά")),
    "4x3": lambda d: make_deck(d, text_box("old deck"), size=STANDARD),
    "google_size": lambda d: make_deck(d, text_box("google", x=-0.3), size=GOOGLE),
    "canva_size": lambda d: make_deck(d, text_box("canva", x=-0.56, w=18), size=CANVA),
    "off_slide_text": lambda d: make_deck(d, text_box("left of slide", x=-0.56), picture(x=-2)),
    "canva_fonts": lambda d: make_deck(
        d, text_box("T", font="Calibri (MS) Bold"), text_box("B", font="Calibri (MS)"),
        text_box("Q", font="Roboto Bold"), text_box("M", font="Montserrat SemiBold"),
        group(text_box("G", font="Canva Sans")), size=CANVA,
        embeds=[embed("Calibri (MS)", "regular", "Calibri (MS)"),
                embed("Calibri (MS) Bold", "regular", "Calibri (MS)", "Bold"),
                embed("Roboto", "regular", "Roboto", compressed=True),
                embed("Roboto Bold", "regular", "Roboto", "Bold")]),
}
