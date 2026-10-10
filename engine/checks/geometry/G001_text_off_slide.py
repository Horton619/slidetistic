from engine.core import EMU_PER_INCH, Check, Finding, FixRefused, Status, inches
from engine.core.layout.pdf import drawn_text
from engine.core.text_geometry import alignments, anchored_edge_off, text_overhang, text_start_offset


class TextOffSlide(Check):
    id = "G001"
    title = "Text off the slide"
    group = "geometry"
    description = ("Text off the left, right or top edge. With PowerPoint available it judges the words as drawn, "
                   "not the box. Pictures are allowed off-slide and never flagged.")
    default_fix = True
    sources = ["canva", "google", "any"]
    thresholds = ["slide_margin_in", "offslide_tolerance_in"]

    def detect(self, deck, ctx):
        tol = self.threshold(ctx, "offslide_tolerance_in") * EMU_PER_INCH
        W = deck.slide_width
        findings = []
        for sv in deck.iter_shapes():
            if not sv.text_bearing or sv.bounds is None or sv.rotation or sv.flipped:
                continue   # rotated/flipped text: G003
            b = sv.bounds
            # Only the area text can occupy counts: a box overhanging by less than its own inner
            # margin cuts nothing off (PAT: 0.04-0.14 in top overhangs, all harmless).
            room = text_overhang(sv.shape, b, W, deck.slide_height)
            edges = [e for e in ("left", "right", "top") if room[e] > tol]
            if not edges:
                continue
            over = max(-b.left, b.right - W, -b.top)
            box = f"box x {inches(b.left)}–{inches(b.right)} in, y from {inches(b.top)} in on a {inches(W)} in slide"
            drawn = drawn_text(ctx.layout, deck, sv, tol)
            if drawn is not None and drawn.total:
                # David 2026-10-10: box overhangs flagged far too often; only the words matter.
                lost = [e for e in drawn.off_edges if e != "bottom"]
                if not drawn.missing and not lost:
                    continue
                rule = (f"PowerPoint render: {drawn.drawn} of {drawn.total} words drawn"
                        + (f", drawn text x {inches(drawn.bounds[0])}–{inches(drawn.bounds[2])} in" if drawn.bounds else "")
                        + f"; {box}. Words outside the slide are left out of the render.")
                status = Status.RED
                msg = (f"{drawn.missing} of {drawn.total} words are off the {' or '.join(edges)} edge of the slide."
                       if drawn.missing else f"Text is drawn past the {' and '.join(lost)} edge of the slide.")
                findings.append(Finding(self.id, status, msg, slide=sv.slide_number, shape_id=sv.shape_id,
                    shape_name=sv.name, subject="off-slide",
                    evidence={"rule": rule, "edges": edges, "overhang_in": inches(over), "words_drawn": drawn.drawn,
                              "words_total": drawn.total, "box_in": [inches(b.left), inches(b.top), inches(b.width),
                              inches(b.height)], "in_group": sv.group_depth > 0}))
                continue
            certain = anchored_edge_off(sv.shape, b, W, tol)
            algn = ",".join(sorted(alignments(sv.shape))) or "none"
            rule = (f"{box}; "
                    f"alignment {algn}; text can start {inches(text_start_offset(sv.shape))} in inside the box's left "
                    f"edge (margin + indent). "
                    + ("Text is pinned to the off-slide edge, so the words are cut off." if certain else
                       "Not pinned to that edge, so the words may still be on the slide (needs the layout check)."))
            if certain:
                status, msg = Status.RED, (f"Text starts off the {certain} edge of the slide "
                                           f"(box is {inches(over)} in past it), so the first words are cut off.")
            else:
                status, msg = Status.YELLOW, (f"Text box runs {inches(over)} in past the {' and '.join(edges)} edge. "
                                              f"The words may still be on the slide; check it in the visual review.")
            findings.append(Finding(self.id, status, msg, slide=sv.slide_number, shape_id=sv.shape_id,
                shape_name=sv.name, subject="off-slide",
                evidence={"rule": rule, "edges": edges, "overhang_in": inches(over), "box_in": [inches(b.left), inches(b.top),
                          inches(b.width), inches(b.height)], "in_group": sv.group_depth > 0}))
        return findings

    def fix(self, deck, finding, edits, ctx):
        if finding.status != Status.RED:
            raise FixRefused("can't tell yet whether the words themselves are off the slide")
        sv = deck.find_shape(finding.slide, finding.shape_id)
        if sv.group_depth:
            raise FixRefused("it's inside a group (fixes inside groups come later)")
        margin = self.threshold(ctx, "slide_margin_in") * EMU_PER_INCH
        W, b = deck.slide_width, sv.bounds
        if b.width > W - 2 * margin:
            raise FixRefused("the box is wider than the slide; it needs resizing by hand")
        left = margin if b.left < 0 else (W - margin - b.width if b.right > W else None)
        top = margin if b.top < 0 else None
        edits.set_geometry(sv, left=left, top=top)
