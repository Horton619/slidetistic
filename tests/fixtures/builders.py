"""Tiny decks built in code. Each helper returns a function that adds one shape to a shape tree.

    path = make_deck(tmp_path, text_box(x=-0.5, text="hi", font="Roboto Bold"))
    path = make_deck(tmp_path, slides=[[title("A")], [picture(x=-1)]], size=CANVA)
"""
from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

WIDE = (13.333, 7.5)        # PowerPoint 16:9
GOOGLE = (10, 5.625)
CANVA = (20, 11.25)
STANDARD = (10, 7.5)        # 4:3


def text_box(text="Text", x=1, y=1, w=4, h=1, font=None, size=None, rotation=0, name=None):
    def add(shapes):
        tb = shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tb.text_frame.text = text
        run = tb.text_frame.paragraphs[0].runs[0]
        if font:
            run.font.name = font
        if size:
            run.font.size = Pt(size)
        if rotation:
            tb.rotation = rotation
        if name:
            tb.name = name
        return tb
    return add


def picture(x=1, y=1, w=2, h=2):
    def add(shapes):
        return shapes.add_picture(io.BytesIO(_png()), Inches(x), Inches(y), Inches(w), Inches(h))
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


def make_deck(folder: Path, *shapes, slides=None, size=WIDE, notes=None, layout=6,
              titles=None, name="deck.pptx") -> Path:
    """`shapes` fills one slide; `slides` is a list of shape lists. layout 6 = Blank, 0/1 have placeholders."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(size[0]), Inches(size[1])
    for i, slide_shapes in enumerate(slides if slides is not None else [list(shapes)]):
        slide = prs.slides.add_slide(prs.slide_layouts[layout])
        for add in slide_shapes:
            add(slide.shapes)
        if titles and slide.shapes.title is not None:
            slide.shapes.title.text = titles[i]
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    path = Path(folder) / name
    prs.save(str(path))
    return path


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
}
