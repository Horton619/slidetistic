from engine.core import Check, Finding, FixRefused, Status
from engine.core import fit
from engine.core.layout.pdf import EMU_PER_PT


class TextOverlapsText(Check):
    id = "L010"
    title = "Text overlaps text"
    group = "layout"
    description = "Two text boxes whose drawn text overlaps. (Boxes overlapping is fine; the words colliding is not.)"
    default_fix = True          # David 2026-10-10: fix it, don't just flag it
    requires = ["layout"]
    sources = ["any"]
    thresholds = ["safe_zone_pct", "overlap_min_pt", "fit_max_font_shrink_pct", "fit_min_line_spacing_pct", "body_widen_max_pct"]

    def detect(self, deck, ctx):
        if ctx.layout is None:
            return []
        tol = self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT
        names = {(sv.slide_number, sv.shape_id): sv.name for sv in deck.iter_shapes()}
        findings = []
        for n in range(1, len(deck.slides) + 1):
            shapes = [st for st in ctx.layout.slide(n).values() if st.lines]
            for i, a in enumerate(shapes):
                for b in shapes[i + 1:]:
                    hit = _first_overlap(a.lines, b.lines, tol)
                    if hit:
                        la, lb = hit
                        # Report it on the box whose wrapped line caused it, so the fix starts there.
                        findings.append(Finding(self.id, Status.RED,
                            f"Text of '{names.get((n, a.shape_id))}' collides with '{names.get((n, b.shape_id))}' "
                            f"(\"{' '.join(la.words)[:30]}\" over \"{' '.join(lb.words)[:30]}\").",
                            slide=n, shape_id=a.shape_id, shape_name=names.get((n, a.shape_id)),
                            subject=f"with {b.shape_id}",
                            evidence={"other_shape": b.shape_id, "lines": [_desc(la), _desc(lb)],
                                      "box_emu": [min(la.left, lb.left), min(la.top, lb.top),
                                                  max(la.right, lb.right), max(la.bottom, lb.bottom)],
                                      "rule": "drawn lines overlap sideways and by more than a quarter of a line's height vertically"}))
        return findings


    def fix(self, deck, finding, edits, ctx):
        """Re-wrap one of the two boxes so their text no longer collides (PAT 5, 24): cheapest change,
        box → font, that predicts no collision, no new single-word lines or extra lines, inside the
        safe zone, onto no picture."""
        layout = ctx.layout.slide(finding.slide)
        safe = fit.safe_rect(deck, self.threshold(ctx, "safe_zone_pct"))
        tol = self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT
        fonts, _ = fit.choices(ctx, self.threshold)
        for sid in (finding.shape_id, finding.evidence["other_shape"]):
            st, sv = layout.get(sid), deck.find_shape(finding.slide, sid)
            if not st or not st.lines or not sv or sv.rotation:
                continue
            _, orphans_now, lines_now = fit.Reflow(sv, st).predict(sv.bounds.left, sv.bounds.width)
            limit = fit.header_limit(deck, sv, layout, ctx)
            widen = max(0, int(((safe[2] - safe[0]) / sv.bounds.width - 1) * 100) + 1)
            plan = fit.plan_fit(deck, sv, st, layout, safe, tol, narrow_pct=15, widen_pct=widen, fonts=fonts,
                                obstacle_boxes=fit.obstacles(deck, finding.slide, sid, st.lines),
                                accept=lambda o, t: o <= orphans_now and t <= lines_now
                                and (limit is None or t <= limit))
            if plan and fit.apply(edits, sv, plan, "clear colliding text"):
                return
        raise FixRefused("no width or font size (within the caps) separates these texts without other "
                         "problems; move one by hand")


def _first_overlap(lines_a, lines_b, tol):
    """Rendered line boxes include the font's full ascent/descent, so neighbouring lines' boxes touch by
    a few points without the letters meeting (PAT slide 27): fit.lines_collide has the rule."""
    for la in lines_a:
        for lb in lines_b:
            if fit.lines_collide(la, lb, tol):
                return la, lb
    return None


def _desc(line) -> str:
    return " ".join(line.words)[:40]
