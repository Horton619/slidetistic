from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.opc.package import XmlPart
from pptx.oxml.ns import qn

from .geometry import Bounds, Transform
from .shapes import GROUP, classify, has_text


@dataclass
class ShapeView:
    slide_index: int               # 0-based
    shape: object                  # python-pptx shape
    kind: str
    bounds: Bounds | None          # absolute, EMU; None when position is unknown
    group_depth: int               # 0 = directly on the slide
    rotation: float
    flipped: bool
    text_bearing: bool
    xf: Transform = None           # maps the shape's own coordinates to slide coordinates

    @property
    def slide_number(self) -> int:
        return self.slide_index + 1

    @property
    def shape_id(self) -> int:
        return self.shape.shape_id

    @property
    def name(self) -> str:
        return self.shape.name


class Deck:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.prs = Presentation(str(self.path))
        # python-pptx keeps some XML parts (theme, presProps) as raw bytes. We parse them on
        # demand and write them back in save(), so edits to them go through the same path.
        self._blob_roots: dict[str, tuple[object, etree._Element]] = {}

    @property
    def slide_width(self) -> int:
        return self.prs.slide_width

    @property
    def slide_height(self) -> int:
        return self.prs.slide_height

    @property
    def slides(self):
        # prs.slides calls get_or_add_sldIdLst(), which writes an empty <p:sldIdLst> into a
        # slideless deck. Reading must never change the deck, so check for it first.
        if self.prs.part._element.sldIdLst is None:
            return []
        return list(self.prs.slides)

    def iter_shapes(self) -> list[ShapeView]:
        """Every shape on every slide, groups included, children of groups flattened in."""
        out: list[ShapeView] = []
        for i, slide in enumerate(self.slides):
            self._walk(i, slide.shapes, Transform(), 0, out)
        return out

    def _walk(self, slide_index, shapes, xf: Transform, depth: int, out: list):
        for shape in shapes:
            kind = classify(shape)
            bounds = None
            if None not in (shape.left, shape.top, shape.width, shape.height):
                bounds = xf.apply(shape.left, shape.top, shape.width, shape.height)
            xfrm = _xfrm(shape)
            out.append(ShapeView(
                slide_index=slide_index,
                shape=shape,
                kind=kind,
                bounds=bounds,
                group_depth=depth,
                rotation=getattr(shape, "rotation", 0.0) or 0.0,
                flipped=xfrm is not None and (xfrm.get("flipH") == "1" or xfrm.get("flipV") == "1"),
                text_bearing=has_text(shape),
                xf=xf,
            ))
            if kind == GROUP:
                child_xf = xf.child_transform(xfrm) if xfrm is not None else xf
                self._walk(slide_index, shape.shapes, child_xf, depth + 1, out)

    def slide_shapes(self, slide_number: int) -> list[ShapeView]:
        """iter_shapes() for one slide (1-based). Walking every slide to keep one made layout repair
        quadratic in slide count: each walk resolves placeholder inheritance through python-pptx."""
        slides = self.slides
        if not 1 <= slide_number <= len(slides):
            return []
        out: list[ShapeView] = []
        self._walk(slide_number - 1, slides[slide_number - 1].shapes, Transform(), 0, out)
        return out

    def find_shape(self, slide_number: int, shape_id: int) -> ShapeView | None:
        for sv in self.slide_shapes(slide_number):
            if sv.shape_id == shape_id:
                return sv
        return None

    def xml_parts(self) -> list[tuple[object, etree._Element]]:
        """(part, root element) for every XML part, excluding embedded font data."""
        out = []
        for part in self.prs.part.package.iter_parts():
            name = str(part.partname)
            if not name.endswith(".xml") or name.startswith("/ppt/fonts/"):
                continue
            if isinstance(part, XmlPart):
                out.append((part, part._element))
            else:
                if name not in self._blob_roots:
                    self._blob_roots[name] = (part, etree.fromstring(part.blob))
                out.append(self._blob_roots[name])
        return out

    def slide_number_of(self, part) -> int | None:
        for i, slide in enumerate(self.slides):
            if slide.part is part:
                return i + 1
        return None

    def save(self, out_path: str | os.PathLike) -> Path:
        """Atomic: write to a temp name beside the target, then rename over it."""
        for part, root in self._blob_roots.values():
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        out_path = Path(out_path)
        tmp = out_path.with_name(out_path.name + ".partial")
        self.prs.save(str(tmp))
        os.replace(tmp, out_path)
        return out_path

    def part_blobs(self) -> dict[str, bytes]:
        """Serialized bytes of every part. Used to prove a step changed nothing."""
        return {str(p.partname): p.blob for p in self.prs.part.package.iter_parts()}


def _xfrm(shape):
    el = shape.element
    for path in ("p:spPr/a:xfrm", "p:grpSpPr/a:xfrm", "p:xfrm"):
        found = el.find("/".join(qn(t) for t in path.split("/")))
        if found is not None:
            return found
    return None
