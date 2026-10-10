"""Visual review: which shapes changed, where to draw boxes, and the before/after images."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .core import Deck, Status
from .core.content import is_hidden
from .core.shapes import GROUP


KIND = {"F": "font", "G": "placement", "L": "layout", "M": "media", "P": "media", "C": "content", "X": "content"}
KIND_LABEL = {"font": "Font fix", "placement": "Placement", "layout": "Layout fit", "media": "Media & playback",
              "content": "Content"}
TIERS = {1: "Broken: fix before the show", 2: "Changes SlideTistic made: check them",
         3: "Needs a look", 4: "Changed underneath, looks identical"}


def kind_of(check_id: str) -> str:
    return KIND.get(check_id[:1], "content")


@dataclass
class Box:
    left: float      # % of slide width/height
    top: float
    width: float
    height: float
    label: str       # what happened, one line
    kind: str        # font | placement | layout | media | content  (box colour)
    mode: str        # changed | red | yellow                          (line style / severity)
    detail: str = "" # diagnostic: the rule and numbers behind it


@dataclass
class SlideVisual:
    slide: int
    before_boxes: list[Box] = field(default_factory=list)
    after_boxes: list[Box] = field(default_factory=list)
    before_png: str | None = None    # data: URI
    after_png: str | None = None
    looks_same: bool = False         # rendered before/after are visually identical

    @property
    def tier(self) -> int:
        modes = {b.mode for b in self.after_boxes + self.before_boxes}
        if "red" in modes:
            return 1
        if not self.looks_same and any(b.mode == "changed" for b in self.after_boxes):
            return 2
        if "yellow" in modes:
            return 3
        return 4

    @property
    def needs_eyes(self) -> bool:
        return self.tier < 4


def changed_shapes(original: Path, mended: Path) -> dict[tuple[int, int], tuple]:
    """(slide, shape id) → (before ShapeView, after ShapeView) for every shape whose XML differs."""
    before = {(s.slide_number, s.shape_id): s for s in Deck(original).iter_shapes() if s.kind != GROUP}
    after = {(s.slide_number, s.shape_id): s for s in Deck(mended).iter_shapes() if s.kind != GROUP}
    return {k: (before[k], after[k]) for k in before.keys() & after.keys()
            if etree.tostring(before[k].shape.element) != etree.tostring(after[k].shape.element)}


def plan(result, original: Path, mended: Path | None) -> list[SlideVisual]:
    """Every slide worth a look, with boxes: changed shapes (before + after) and open findings (current)."""
    current = Deck(mended or original)
    W, H = current.slide_width, current.slide_height
    visuals: dict[int, SlideVisual] = {}

    def pct(l, t, r, b) -> tuple[float, float, float, float]:
        return 100 * l / W, 100 * t / H, 100 * (r - l) / W, 100 * (b - t) / H

    def from_sv(sv):
        bd = sv.bounds
        return pct(bd.left, bd.top, bd.right, bd.bottom)

    if mended:
        per_shape: dict[tuple, list] = {}
        for c in result.changes:
            if c.slide and c.shape_id:
                per_shape.setdefault((c.slide, c.shape_id), []).append(c)
        fixed = {f.key: f for f in result.findings if f.status == Status.GREEN_FIXED}
        deck_fixes = [f for f in fixed.values() if not f.slide]
        for (slide, sid), (b, a) in changed_shapes(original, mended).items():
            changes = per_shape.get((slide, sid), [])
            if changes:
                cid = changes[0].check_id
                label = _change_label(changes)
                rule = next((f.evidence.get("rule", "") for f in fixed.values()
                             if f.slide == slide and f.shape_id == sid), "")
            else:   # touched by a deck-wide fix (font renames, embedded list)
                cid = deck_fixes[0].check_id if deck_fixes else "F"
                label = "Deck-wide fix: " + ", ".join(f"{f.check_id} {f.subject}" for f in deck_fixes[:4])
                rule = " | ".join(f"{f.check_id}: {f.evidence.get('rule', f.message)}" for f in deck_fixes[:4])
            v = visuals.setdefault(slide, SlideVisual(slide))
            if b.bounds:
                v.before_boxes.append(Box(*from_sv(b), label, kind_of(cid), "changed", rule))
            if a.bounds:
                v.after_boxes.append(Box(*from_sv(a), label, kind_of(cid), "changed", rule))

    shapes = {(s.slide_number, s.shape_id): s for s in current.iter_shapes()}
    for f in result.findings:
        if f.status not in (Status.RED, Status.YELLOW) or not f.slide:
            continue
        if "box_emu" in f.evidence:            # layout checks outline the drawn text itself
            geom = pct(*f.evidence["box_emu"])
        elif f.shape_id and (f.slide, f.shape_id) in shapes and shapes[(f.slide, f.shape_id)].bounds:
            geom = from_sv(shapes[(f.slide, f.shape_id)])
        else:
            continue
        v = visuals.setdefault(f.slide, SlideVisual(f.slide))
        target = v.after_boxes if mended else v.before_boxes
        target.append(Box(*geom, f"{f.check_id}: {f.message}", kind_of(f.check_id), f.status.value,
                          f.evidence.get("rule", "")))
    return [visuals[k] for k in sorted(visuals)]


def render(visuals: list[SlideVisual], original: Path, mended: Path, renderer, image_dir: Path | None = None) -> None:
    """Fill in before/after images. PowerPoint's PDF leaves out hidden slides, so map numbers to pages.
    With `image_dir`, images are written there as files (the app's review bundle) and the visuals hold
    their file names; otherwise they're embedded as data: URIs (the stand-alone HTML report)."""
    if not visuals:
        return
    pages = {}
    for label, path in (("before", original), ("after", mended)) if mended else (("before", original),):
        hidden = [is_hidden(s) for s in Deck(path).slides]
        page_of = {}
        page = 0
        for n, h in enumerate(hidden, 1):
            if not h:
                page += 1
                page_of[n] = page
        pages[label] = (renderer.to_pdf(path, label), page_of)
    for v in visuals:
        raw = {}
        for label, attr in (("before", "before_png"), ("after", "after_png")):
            if label not in pages:
                continue
            pdf, page_of = pages[label]
            if v.slide in page_of:
                raw[label] = renderer.page_image(pdf, page_of[v.slide])
                if image_dir:
                    name = f"slide-{v.slide}-{label}.jpg"
                    (image_dir / name).write_bytes(raw[label])
                    setattr(v, attr, name)
                else:
                    setattr(v, attr, "data:image/jpeg;base64," + base64.b64encode(raw[label]).decode())
        if len(raw) == 2:
            v.looks_same = _same_picture(raw["before"], raw["after"])


def _same_picture(a: bytes, b: bytes, noise: int = 40) -> bool:
    """True when two renders differ only by JPEG noise (font renames that don't change the look)."""
    import io
    from PIL import Image, ImageChops
    ia, ib = Image.open(io.BytesIO(a)).convert("L"), Image.open(io.BytesIO(b)).convert("L")
    if ia.size != ib.size:
        return False
    return ImageChops.difference(ia, ib).point(lambda v: 255 if v > noise else 0).getbbox() is None


GEOMETRY = {"left": "position", "top": "position", "width": "width", "height": "height"}


def _change_label(changes) -> str:
    """One readable line per property, first value → last value (a fix nudged in rounds would otherwise
    list every step, in EMU: CLARB 11 showed seven 'L009 width: 2948755 → 2919267' entries)."""
    from engine.core import EMU_PER_INCH
    first, last = {}, {}
    for c in changes:
        key = (c.check_id, c.prop)
        first.setdefault(key, c.before)
        last[key] = c.after
    out = []
    for (cid, prop), before in first.items():
        after = last[(cid, prop)]
        if prop in GEOMETRY and isinstance(before, int) and isinstance(after, int):
            name = {"left": "moved right" if after > before else "moved left",
                    "top": "moved down" if after > before else "moved up"}.get(prop, prop)
            out.append(f"{cid} {name}: {before / EMU_PER_INCH:.2f} → {after / EMU_PER_INCH:.2f} in")
        else:
            out.append(f"{cid} {prop}: {before} → {after}")
    return "; ".join(out)

