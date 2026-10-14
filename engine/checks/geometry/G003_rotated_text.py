from engine.core import Check, Finding, Status


class RotatedText(Check):
    id = "G003"
    title = "Rotated or flipped text"
    group = "geometry"
    description = "Text that's rotated or flipped. Left out of automatic geometry fixes; check it by eye."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        out = []
        for sv in deck.iter_shapes():
            if not sv.text_bearing:
                continue
            vert = _vertical(sv)
            if not (sv.rotation or sv.flipped or vert):
                continue
            what = ("Text is flipped" if sv.flipped else f"Text is rotated {round(sv.rotation)}°" if sv.rotation
                    else "Text runs vertically (text direction)")
            out.append(Finding(self.id, Status.YELLOW, what + ". SlideTistic won't move it automatically.",
                               slide=sv.slide_number, shape_id=sv.shape_id, shape_name=sv.name, subject="rotated",
                               evidence={"rotation": round(sv.rotation, 1), "flipped": sv.flipped, "vert": vert}))
        return out


def _vertical(sv) -> str | None:
    """The box's text direction when it isn't horizontal (bodyPr vert: 'vert', 'vert270', 'eaVert', …). Sideways
    text without any rotation (adversarial round 1: Google exports set it this way)."""
    from pptx.oxml.ns import qn
    tf = getattr(sv.shape, "text_frame", None) if getattr(sv.shape, "has_text_frame", False) else None
    body = tf._txBody.find(qn("a:bodyPr")) if tf is not None else None
    vert = body.get("vert") if body is not None else None
    return vert if vert and vert != "horz" else None
