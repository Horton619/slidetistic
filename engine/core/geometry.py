"""Absolute geometry for shapes, including shapes nested inside groups.

A group maps its children's coordinate space (chOff/chExt) onto its own box (off/ext).
Nested groups compose those mappings. All values are EMU.
"""
from __future__ import annotations

from dataclasses import dataclass

from pptx.oxml.ns import qn

EMU_PER_INCH = 914400


def inches(emu: int | float) -> float:
    return round(emu / EMU_PER_INCH, 2)


@dataclass(frozen=True)
class Transform:
    """x_abs = off_x + x * scale_x (same for y)."""
    scale_x: float = 1.0
    scale_y: float = 1.0
    off_x: float = 0.0
    off_y: float = 0.0

    def apply(self, x: float, y: float, cx: float, cy: float) -> "Bounds":
        return Bounds(
            left=self.off_x + x * self.scale_x,
            top=self.off_y + y * self.scale_y,
            width=cx * self.scale_x,
            height=cy * self.scale_y,
        )

    def child_transform(self, group_xfrm) -> "Transform":
        """Transform for the children of a group whose a:xfrm / p:xfrm element is `group_xfrm`."""
        off, ext = group_xfrm.find(qn("a:off")), group_xfrm.find(qn("a:ext"))
        ch_off, ch_ext = group_xfrm.find(qn("a:chOff")), group_xfrm.find(qn("a:chExt"))
        if off is None or ext is None or ch_off is None or ch_ext is None:
            return self
        ch_cx, ch_cy = int(ch_ext.get("cx")), int(ch_ext.get("cy"))
        sx = int(ext.get("cx")) / ch_cx if ch_cx else 1.0
        sy = int(ext.get("cy")) / ch_cy if ch_cy else 1.0
        # Local: x_grp = off.x + (x - chOff.x) * sx; then map through this (outer) transform.
        lx = int(off.get("x")) - int(ch_off.get("x")) * sx
        ly = int(off.get("y")) - int(ch_off.get("y")) * sy
        return Transform(
            scale_x=self.scale_x * sx,
            scale_y=self.scale_y * sy,
            off_x=self.off_x + lx * self.scale_x,
            off_y=self.off_y + ly * self.scale_y,
        )


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def crosses_slide(self, slide_w: int, slide_h: int) -> bool:
        return self.left < 0 or self.top < 0 or self.right > slide_w or self.bottom > slide_h

