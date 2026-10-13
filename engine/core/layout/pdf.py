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


def _same_lines(a: list, b: list, tol: float = 6350) -> bool:
    """Two renders of one slide agree: the same words on the same lines, within half a point."""
    return len(a) == len(b) and all(
        la.words == lb.words and all(abs(x - y) <= tol for x, y in ((la.left, lb.left), (la.top, lb.top),
                                                                    (la.right, lb.right), (la.bottom, lb.bottom)))
        for la, lb in zip(a, b))


class PdfLayout:
    """LayoutProvider (SPEC §6) backed by PowerPoint's PDF. Renders lazily, once per deck file."""
    name = "PowerPoint (PDF)"
    confidence = "high"

    def __init__(self, deck, renderer, path=None, only=None, base=None, check=False):
        """`path`: the file to render when it isn't deck.path (the working copy during repair).
        `only` + `base` (changed-slide export, review 2026-10-13 3.10): PowerPoint draws just the slides in `only`;
        every other slide is unchanged since `base` was drawn and keeps base's render. `check`: draw the whole
        deck too and use that, recording in `partial_mismatch` any changed slide whose partial render differs."""
        self.deck, self.renderer, self.path = deck, renderer, path
        self.only, self.base, self.check = only, base, check
        self._pages: dict[int, list[Line]] | None = None
        self._by_slide: dict[int, dict[int, ShapeText]] = {}
        self._pdf = None
        self._page_of: dict[int, int] = {}
        self._src: dict[int, tuple] = {}          # slide → (layout that drew it, pdf, page)
        self._gray: dict[int, object] = {}
        self.export_s: float | None = None
        self.partial_mismatch: list[int] | None = None

    def _pdf_pages(self, path, label):
        import time
        t0 = time.monotonic()
        pdf = self.renderer.to_pdf(path, label)
        self.export_s = (self.export_s or 0) + time.monotonic() - t0
        out = subprocess.run([tools.find("pdftotext") or "pdftotext", "-bbox-layout", str(pdf), "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                             check=True).stdout
        return pdf, parse_bbox_html(out)

    def _load(self):
        if self._pages is not None:
            return
        from ..content import is_hidden
        visible = [n for n, slide in enumerate(self.deck.slides, 1) if not is_hidden(slide)]
        if self.only is not None and self.base is not None:
            partial = self._load_partial(visible)
            if not self.check:
                return
            self._pages, self._src, self._page_of = None, {}, {}
        pdf, pages = self._pdf_pages(self.path or self.deck.path, "layout")
        self._pdf = pdf
        self._pages = {}
        for page, n in enumerate(visible, 1):
            self._pages[n] = pages.get(page, [])
            self._page_of[n] = page
            self._src[n] = (self, pdf, page)
        if self.only is not None and self.base is not None:
            self.partial_mismatch = [n for n in sorted(partial) if not _same_lines(partial[n], self._pages[n])]

    def _load_partial(self, visible: list[int]) -> dict[int, list]:
        import tempfile
        from ..partial import write_subset
        self.base._load()
        changed = [n for n in visible if n in self.only]
        self._pages = {}
        for n in visible:
            if n not in self.only:
                self._pages[n] = self.base._pages.get(n, [])
                self._src[n] = self.base._src.get(n)
        drawn = {}
        if changed:
            src = Path(self.path or self.deck.path)
            with tempfile.TemporaryDirectory() as tmp:
                sub = Path(tmp) / f"{src.stem}-changed.pptx"
                kept = write_subset(src, sub, set(changed))
                pdf, pages = self._pdf_pages(sub, "changed")
            for page, n in enumerate(kept, 1):
                drawn[n] = self._pages[n] = pages.get(page, [])
                self._src[n] = (self, pdf, page)
            self._pdf = pdf
        return drawn

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

    # --- ink: what the letters actually cover (David 2026-10-12) --------------------------------------
    # A line box spans the font's whole ascent and descent, far more than the letters (a script title's box
    # reached 1 in above its tallest letter). Two boxes overlapping, or a box crossing the slide edge, says
    # little; the rendered picture says whether letters really meet or are cut off.

    def page_gray(self, slide_number: int):
        """The slide as PowerPoint drew it, greyscale (PIL), ~120 px per inch. None without a render."""
        if slide_number not in self._gray:
            self._load()
            owner, pdf, page = self._src.get(slide_number) or (None, None, None)
            if owner is not None and owner is not self:
                return owner.page_gray(slide_number)       # unchanged slide: the earlier render's picture
            img = None
            if page and pdf is not None and hasattr(self.renderer, "page_image"):
                import io
                from PIL import Image
                width = int(self.deck.slide_width / 914400 * 120)
                img = Image.open(io.BytesIO(self.renderer.page_image(pdf, page, width=width))).convert("L")
            self._gray[slide_number] = img
        return self._gray[slide_number]

    def _crop(self, slide_number, left, top, right, bottom):
        img = self.page_gray(slide_number)
        if img is None:
            return None
        sx, sy = img.width / self.deck.slide_width, img.height / self.deck.slide_height
        box = (max(0, int(left * sx)), max(0, int(top * sy)), min(img.width, int(right * sx) + 1),
               min(img.height, int(bottom * sy) + 1))
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            return None
        return img.crop(box)

    def letters_apart(self, slide_number: int, a: Line, b: Line) -> bool | None:
        """True when the picture shows a clean pixel row with letters above it AND letters below it, between
        the two lines' letter zones, where they overlap sideways (stacked map labels: 'IL' over '331').
        A blank row with ink on one side only is just the empty space inside a line (above the capitals,
        below the baseline): it proves nothing, so text drawn over text still counts. None without a picture."""
        from ..fit import letter_zone
        x0, x1 = max(a.left, b.left), min(a.right, b.right)
        if x1 <= x0:
            return True
        (ta, ba), (tb, bb) = letter_zone(a), letter_zone(b)
        pad = max(a.bottom - a.top, b.bottom - b.top)
        around = self._crop(slide_number, min(a.left, b.left) - pad, min(a.top, b.top) - pad,
                            max(a.right, b.right) + pad, max(a.bottom, b.bottom) + pad)
        zone = self._crop(slide_number, x0, min(ta, tb), x1, max(ba, bb))
        if around is None or zone is None:
            return None
        bg = _background(around)
        px, w = zone.load(), zone.width
        allow = max(1, w // 200)
        inked = [sum(1 for x in range(w) if abs(px[x, y] - bg) > INK_DIFF) > allow for y in range(zone.height)]
        seen_ink = False
        for y, ink in enumerate(inked):
            if ink:
                seen_ink = True
            elif seen_ink and any(inked[y + 1:]):
                return True
        return False

    def cut_off(self, slide_number: int, line: Line, edge: str) -> bool | None:
        """True when letters of `line` touch the slide `edge` in the picture (really cut off); False when the
        edge is clean there (only the line box crosses it). None when there's no picture."""
        W, H = self.deck.slide_width, self.deck.slide_height
        strip_px = 2 * 914400 / 120                     # the outermost ~2 pixels
        rect = {"top": (line.left, 0, line.right, strip_px), "bottom": (line.left, H - strip_px, line.right, H),
                "left": (0, line.top, strip_px, line.bottom), "right": (W - strip_px, line.top, W, line.bottom)}[edge]
        near = {"top": (line.left, 0, line.right, max(line.bottom, strip_px)),
                "bottom": (line.left, min(line.top, H - strip_px), line.right, H),
                "left": (0, line.top, max(line.right, strip_px), line.bottom),
                "right": (min(line.left, W - strip_px), line.top, W, line.bottom)}[edge]
        strip, around = self._crop(slide_number, *rect), self._crop(slide_number, *near)
        if strip is None or around is None:
            return None
        bg = _background(around)
        return sum(1 for v in strip.getdata() if abs(v - bg) > INK_DIFF) > 2


INK_DIFF = 60          # grey levels between a letter pixel and the background around it (JPEG noise is < 40)


def _background(img) -> int:
    """The most common grey level, in bands of 8 (letters cover well under half of the area around them)."""
    hist = img.histogram()
    bands = [sum(hist[i:i + 8]) for i in range(0, 256, 8)]
    best = max(range(len(bands)), key=bands.__getitem__)
    return best * 8 + 4


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
