"""Picture facts for the image checks: pixel size, file size, and how big it's shown."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image as PILImage

from .deck import ShapeView
from .shapes import PICTURE

# We only read image headers for their size; real decks hold 95-megapixel photos (corpus 2026-10-09),
# which trips Pillow's default decompression-bomb warning for no reason. A limit stays (review 2026-10-13):
# Pillow refuses images over twice this (400 MP), which a crafted picture could use to fill memory.
PILImage.MAX_IMAGE_PIXELS = 200_000_000

BITMAPS = {"image/png", "image/jpeg", "image/gif", "image/bmp", "image/tiff"}


@dataclass
class Pic:
    sv: ShapeView
    content_type: str
    px_w: int | None
    px_h: int | None
    mb: float
    shown_px: int            # width on a screen `output_width_px` wide
    ratio: float | None      # visible image pixels / shown pixels; None for non-bitmaps


def pictures(deck, output_width_px: int) -> list[Pic]:
    out = []
    for sv in deck.iter_shapes():
        if sv.kind != PICTURE or sv.bounds is None:
            continue
        try:
            image = sv.shape.image
            # python-pptx's image.content_type is sniffed from the bytes; PowerPoint goes by the
            # type the package declares for the part, so use that.
            content_type = sv.shape.part.related_part(sv.shape._element.blip_rId).content_type
        except (ValueError, KeyError, AttributeError):   # linked or missing image
            continue
        shown = max(1, round(sv.bounds.width / deck.slide_width * output_width_px))
        px_w = px_h = ratio = None
        if content_type in BITMAPS:
            try:
                px_w, px_h = image.size
            except Exception:  # noqa: BLE001 — unreadable header: skip the ratio, keep the facts
                pass
        if px_w:
            visible = px_w * max(0.0, 1 - (sv.shape.crop_left or 0) - (sv.shape.crop_right or 0))
            ratio = visible / shown if visible else None
        out.append(Pic(sv, content_type, px_w, px_h, len(image.blob) / 1_048_576, shown, ratio))
    return out
