"""Picture compression for M013 (David 2026-10-11): like PowerPoint's Compress Pictures at 150 ppi with
"Delete cropped areas of pictures". Every deck plays on a 1080p screen, so a picture needs no more pixels
than it fills there; full-resolution phone and camera photos (surgical decks) make files huge and
laptops sluggish for no visible gain.

Rules:
- Target: a picture spanning the whole slide keeps `target_w` pixels across (PowerPoint's 150 ppi on a
  13.33 in slide ≈ 2000 px), scaled to the share of the slide it fills. Slide size doesn't matter (a
  Canva 20 in slide gets the same 1080p result).
- Cropped-off areas are deleted when every use of the picture has the same crop; a picture shown with
  different crops in different places is only resized, so no use loses part of its image.
- Only pictures whose every reference is a picture or picture-filled shape we measured on a slide;
  anything also used by a layout, master or notes page is left alone.
- JPEG stays JPEG (quality `quality`, orientation and colour profile kept); PNG stays PNG (transparency
  and crisp screenshots). A picture is only replaced when the result is at least 10% smaller.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from pptx.oxml.ns import qn
from PIL import Image

Image.MAX_IMAGE_PIXELS = 200_000_000     # real decks hold 95-megapixel photos (see images.py)
DECODE_MAX_PIXELS = 150_000_000          # compressing decodes the whole picture: ~600 MB at this size

KINDS = {"image/jpeg": "JPEG", "image/png": "PNG"}
R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


@dataclass
class Use:
    slide_part: object
    blip_fill: object
    src_rect: object | None
    crop: tuple[int, int, int, int]         # l, t, r, b in 1/100000 of the image
    need_w: float                           # pixels this use needs across its visible part
    need_h: float


@dataclass
class Plan:
    part: object
    fmt: str
    size: tuple[int, int]
    bytes: int
    uses: list[Use] = field(default_factory=list)
    crop: tuple[int, int, int, int] | None = None     # deleted when set
    new_size: tuple[int, int] = (0, 0)

    @property
    def estimate(self) -> int:
        """Rough size after compression (pixel area ratio): good enough to pitch, not to promise."""
        (w, h), (nw, nh) = self.size, self.new_size
        return max(20_000, int(self.bytes * (nw * nh) / max(1, w * h)))


def _blip_fill(sv):
    el = sv.shape.element
    bf = el.find(qn("p:blipFill"))
    if bf is None:
        sp_pr = el.find(qn("p:spPr"))
        bf = sp_pr.find(qn("a:blipFill")) if sp_pr is not None else None
    return bf


def plans(deck, target_w: int) -> list[Plan]:
    W, H = deck.slide_width, deck.slide_height
    target_h = target_w * H / W
    uses: dict[object, list[Use]] = {}
    for sv in deck.iter_shapes():
        bf = _blip_fill(sv) if sv.bounds is not None else None
        blip = bf.find(qn("a:blip")) if bf is not None else None
        r_id = blip.get(R_EMBED) if blip is not None else None
        if not r_id or bf.find(qn("a:tile")) is not None:
            continue
        try:
            part = sv.shape.part.related_part(r_id)
        except KeyError:
            continue
        src = bf.find(qn("a:srcRect"))
        crop = tuple(int(src.get(k, 0)) for k in "ltrb") if src is not None else (0, 0, 0, 0)
        vis_w, vis_h = 1 - (crop[0] + crop[2]) / 100000, 1 - (crop[1] + crop[3]) / 100000
        if vis_w <= 0 or vis_h <= 0:
            continue
        uses.setdefault(part, []).append(Use(sv.shape.part, bf, src, crop,
                                             sv.bounds.width / W * target_w, sv.bounds.height / H * target_h))
    out = []
    for part, us in uses.items():
        fmt = KINDS.get(part.content_type)
        if fmt is None or not _only_measured_refs(deck, part, us):
            continue
        try:
            with Image.open(io.BytesIO(part.blob)) as im:
                w, h = im.size
                if fmt == "PNG" and getattr(im, "is_animated", False):
                    continue
                if w * h > DECODE_MAX_PIXELS:
                    continue
        except Exception:  # noqa: BLE001 — unreadable image: leave it
            continue
        crops = {u.crop for u in us}
        crop = next(iter(crops)) if len(crops) == 1 else None      # same crop everywhere: delete the rest
        if crop is not None and (min(crop) < 0 or crop == (0, 0, 0, 0)):
            crop = None                     # negative = padding, not a crop
        if crop:
            vw, vh = w * (1 - (crop[0] + crop[2]) / 100000), h * (1 - (crop[1] + crop[3]) / 100000)
            scale = max(max(u.need_w for u in us) / vw, max(u.need_h for u in us) / vh)
        else:
            vw, vh = w, h
            scale = max(max(u.need_w / (1 - (u.crop[0] + u.crop[2]) / 100000) for u in us) / w,
                        max(u.need_h / (1 - (u.crop[1] + u.crop[3]) / 100000) for u in us) / h)
        if scale >= 0.9 and not crop:
            continue                        # already about the right size
        scale = min(scale, 1.0)
        plan = Plan(part, fmt, (w, h), len(part.blob), us, crop,
                    (max(1, round(vw * scale)), max(1, round(vh * scale))))
        out.append(plan)
    return out


def _only_measured_refs(deck, part, us: list[Use]) -> bool:
    """True when every reference to this picture is one we measured: no layout, master or notes page
    uses it, and on each slide every <a:blip> pointing at it belongs to a measured picture (not, say,
    the slide's background)."""
    measured = {u.blip_fill.find(qn("a:blip")) for u in us}     # held, so lxml hands back these same objects
    slide_parts = {id(u.slide_part): u.slide_part for u in us}
    for p in deck.prs.part.package.iter_parts():
        r_ids = [r_id for r_id, rel in p.rels.items() if not rel.is_external and rel.target_part is part]
        if not r_ids:
            continue
        if id(p) not in slide_parts:
            return False
        for blip in p._element.iter(qn("a:blip")):
            if blip.get(R_EMBED) in r_ids and blip not in measured:
                return False
    return True


def encode(plan: Plan, quality: int) -> bytes | None:
    """The compressed picture, or None when it wouldn't be at least 10% smaller."""
    with Image.open(io.BytesIO(plan.part.blob)) as im:
        info = dict(im.info)
        img = im
        if plan.crop:
            w, h = im.size
            l, t, r, b = plan.crop
            img = im.crop((round(w * l / 100000), round(h * t / 100000),
                           round(w * (1 - r / 100000)), round(h * (1 - b / 100000))))
        if img.size != plan.new_size:
            img = img.resize(plan.new_size, Image.LANCZOS)
        buf = io.BytesIO()
        extra = {k: info[k] for k in ("icc_profile", "exif") if info.get(k)}
        if plan.fmt == "JPEG":
            img.save(buf, "JPEG", quality=quality, optimize=True, **extra)
        else:
            img.save(buf, "PNG", optimize=True, **{k: v for k, v in extra.items() if k == "icc_profile"})
    data = buf.getvalue()
    return data if len(data) <= 0.9 * plan.bytes else None
