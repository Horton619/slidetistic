"""Layout as PowerPoint draws it: lines and words from PowerPoint's own PDF export.

PowerPoint → PDF (engine.render), then Poppler `pdftotext -bbox-layout` gives every line and word with
its box. Lines are matched to slide shapes by their words. No font measuring of our own (CLAUDE.md
rule 4); confidence is high because PowerPoint did the layout. PDF points map 1:1 onto slide points
(1 pt = 12700 EMU). PowerPoint leaves hidden slides out of the PDF; page numbers skip them.
"""
from __future__ import annotations

import html
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .. import tools

EMU_PER_PT = 12700
WORD = re.compile(r"[\w']+", re.UNICODE)


@dataclass
class Word:
    text: str
    left: float      # EMU
    right: float


@dataclass
class Line:
    left: float      # EMU, slide coordinates
    top: float
    right: float
    bottom: float
    words: list[str]
    boxes: list[Word] = field(default_factory=list)
    block: int = -1                 # pdftotext's text block (lines it grouped together)

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def tokens(self) -> list[str]:
        return [t for w in self.words for t in _tokens(w)]


@dataclass
class ShapeText:
    shape_id: int
    lines: list[Line] = field(default_factory=list)
    paragraph_of_line: list[int] = field(default_factory=list)   # index into the shape's paragraphs

    @property
    def bounds(self) -> tuple[float, float, float, float] | None:
        if not self.lines:
            return None
        return (min(l.left for l in self.lines), min(l.top for l in self.lines),
                max(l.right for l in self.lines), max(l.bottom for l in self.lines))


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in WORD.findall(text)]


def parse_bbox_html(text: str) -> dict[int, list[Line]]:
    """pdftotext -bbox-layout output → {page number: [Line]} (EMU)."""
    pages: dict[int, list[Line]] = {}
    block_id = 0
    for n, page in enumerate(re.findall(r"<page\b.*?</page>", text, re.S), 1):
        lines = []
        for block in re.findall(r"<block\b.*?</block>", page, re.S) or [page]:
            block_id += 1
            # Coordinates can be negative: Windows PowerPoint keeps off-slide text in the PDF, so a line
            # that starts past the left/top edge does too (pdftotext clips its words at the page edge).
            for xm, ym, xM, yM, body in re.findall(
                    r'<line xMin="(-?[\d.]+)" yMin="(-?[\d.]+)" xMax="(-?[\d.]+)" yMax="(-?[\d.]+)">(.*?)</line>', block, re.S):
                boxes = [Word(html.unescape(t), float(wx) * EMU_PER_PT, float(wX) * EMU_PER_PT)
                         for wx, wX, t in re.findall(
                             r'<word xMin="(-?[\d.]+)" yMin="-?[\d.]+" xMax="(-?[\d.]+)" yMax="-?[\d.]+">([^<]+)</word>', body)]
                lines.append(Line(float(xm) * EMU_PER_PT, float(ym) * EMU_PER_PT, float(xM) * EMU_PER_PT,
                                  float(yM) * EMU_PER_PT, [b.text for b in boxes], boxes, block_id))
        pages[n] = lines
    return pages


def assign(lines: list[Line], shapes: list[tuple]) -> dict[int, ShapeText]:
    """Give each rendered word to its shape by reading in order.
    `shapes` = [(shape id, [paragraph text, …], (left, top, right, bottom) EMU or None)].

    Every shape's text is a known word sequence, and PowerPoint draws it top to bottom. Walking the
    drawn words in reading order, a word goes to the shape whose NEXT expected word it is (small skips
    allowed for bullets/odd tokens). That settles words two boxes share ("Health" in the title and the
    body, PAT slide 5) and lines pdftotext merged across boxes ("Overview Did of you Maternal"), and it
    tells us each line's paragraph. Words no shape expects (slide numbers, chart labels) are dropped.
    """
    streams = {sid: [(i, t) for i, para in enumerate(paras) for t in _tokens(para)] for sid, paras, _ in shapes}
    ptr = {sid: 0 for sid in streams}
    last_y = {sid: None for sid in streams}
    placed: dict[tuple[int, int], list[tuple[Word, int]]] = {}       # (sid, line index) → [(word, para)]

    ordered = sorted(enumerate(lines), key=lambda il: (round(il[1].top / EMU_PER_PT / 4), il[1].left))
    for li, line in ordered:
        cy = (line.top + line.bottom) / 2
        pending: list[Word] = []
        for w in sorted(line.boxes, key=lambda b: b.left):
            toks = _tokens(w.text)
            if not toks:
                pending.append(w)
                continue
            best = None
            for sid, stream in streams.items():
                p = ptr[sid]
                for k in range(p, min(p + 4, len(stream))):
                    if stream[k][1] == toks[0]:
                        dist = abs(cy - last_y[sid]) if last_y[sid] is not None else 0
                        cand = (k - p, dist, sid, k)
                        best = cand if best is None or cand < best else best
                        break
            if best is None:            # resync: further ahead in a shape that has the word
                for sid, stream in streams.items():
                    for k in range(ptr[sid], len(stream)):
                        if stream[k][1] == toks[0]:
                            cand = (k - ptr[sid], 0, sid, k)
                            best = cand if best is None or cand < best else best
                            break
            if best is None:
                continue
            _, _, sid, k = best
            ptr[sid] = k + len(toks)
            last_y[sid] = cy
            bucket = placed.setdefault((sid, li), [])
            bucket.extend((b, streams[sid][k][0]) for b in pending)   # bullets ride with the next word
            pending = []
            bucket.append((w, streams[sid][k][0]))

    out = {sid: ShapeText(sid) for sid, _, _ in shapes}
    for (sid, li), items in placed.items():
        words = [w for w, _ in items]
        line = lines[li]
        out[sid].lines.append(Line(min(w.left for w in words), line.top, max(w.right for w in words),
                                   line.bottom, [w.text for w in words], words, line.block))
        out[sid].paragraph_of_line.append(next(p for w, p in items if _tokens(w.text)))
    for st in out.values():
        pairs = sorted(zip(st.lines, st.paragraph_of_line), key=lambda lp: (round(lp[0].top / EMU_PER_PT / 4), lp[0].left))
        st.lines = [l for l, _ in pairs]
        st.paragraph_of_line = [p for _, p in pairs]
    return out


class PdfLayout:
    """LayoutProvider (SPEC §6) backed by PowerPoint's PDF. Renders lazily, once per deck file."""
    name = "PowerPoint (PDF)"
    confidence = "high"

    def __init__(self, deck, renderer, path=None):
        """`path`: the file to render when it isn't deck.path (the working copy during repair)."""
        self.deck, self.renderer, self.path = deck, renderer, path
        self._pages: dict[int, list[Line]] | None = None
        self._by_slide: dict[int, dict[int, ShapeText]] = {}

    def _load(self):
        if self._pages is not None:
            return
        from ..content import is_hidden
        pdf = self.renderer.to_pdf(self.path or self.deck.path, "layout")
        out = subprocess.run([tools.find("pdftotext") or "pdftotext", "-bbox-layout", str(pdf), "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                             check=True).stdout
        pages = parse_bbox_html(out)
        self._pages, page = {}, 0
        for n, slide in enumerate(self.deck.slides, 1):
            if not is_hidden(slide):
                page += 1
                self._pages[n] = pages.get(page, [])

    def slide(self, slide_number: int) -> dict[int, ShapeText]:
        """{shape id: ShapeText} for every text-bearing shape on the slide."""
        if slide_number not in self._by_slide:
            self._load()
            from ..content import shape_text
            svs = [sv for sv in self.deck.slide_shapes(slide_number) if sv.text_bearing]
            shapes = [(sv.shape_id, shape_text(sv.shape).split("\n"),
                       (sv.bounds.left, sv.bounds.top, sv.bounds.right, sv.bounds.bottom) if sv.bounds else None)
                      for sv in svs]
            self._by_slide[slide_number] = assign(self._pages.get(slide_number, []), shapes)
        return self._by_slide[slide_number]

    def measure(self, slide_number: int, shape_id: int) -> ShapeText | None:
        return self.slide(slide_number).get(shape_id)


@dataclass
class Drawn:
    """What PowerPoint actually drew for one text box, against the slide edges."""
    total: int                      # words in the box's text
    drawn: int                      # words found in the render
    bounds: tuple[float, float, float, float] | None
    off_edges: list[str]            # slide edges the drawn text itself crosses

    @property
    def missing(self) -> int:
        return self.total - self.drawn


def drawn_text(layout, deck, sv, tol: float) -> Drawn | None:
    """PowerPoint's PDF leaves out words that fall outside the slide (broken deck slides 18 and 20:
    0/11 and 9/15 words), so "all drawn words are on the slide" only proves anything when every word
    was drawn. None when there's no render to ask (no layout, hidden slide)."""
    from ..content import is_hidden, shape_text
    if layout is None or is_hidden(deck.slides[sv.slide_number - 1]):
        return None
    total = len(_tokens(shape_text(sv.shape)))
    st = layout.measure(sv.slide_number, sv.shape_id)
    drawn = sum(len(l.tokens) for l in st.lines) if st else 0
    b = st.bounds if st else None
    edges = []
    if b:
        W, H = deck.slide_width, deck.slide_height
        edges = [e for e, over in (("left", -b[0]), ("top", -b[1]), ("right", b[2] - W), ("bottom", b[3] - H)) if over > tol]
    return Drawn(total, min(drawn, total), b, edges)
