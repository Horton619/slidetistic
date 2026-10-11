from engine.core import Check, Finding, FixRefused, Status
from engine.core import fit, playback
from engine.core.layout.pdf import EMU_PER_PT


class TextOverlapsText(Check):
    id = "L010"
    title = "Text overlaps text"
    group = "layout"
    description = "Two text boxes whose drawn text overlaps. (Boxes overlapping is fine; the words colliding is not.)"
    default_fix = True          # David 2026-10-10: fix it, don't just flag it
    requires = ["layout"]
    sources = ["any"]
    thresholds = ["overlap_max_per_slide", "fit_wrap_band_pct", "safe_zone_pct", "overlap_min_pt", "fit_max_font_shrink_pct", "fit_min_line_spacing_pct", "body_widen_max_pct"]

    def detect(self, deck, ctx):
        if ctx.layout is None:
            return []
        tol = self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT
        names = {(sv.slide_number, sv.shape_id): sv.name for sv in deck.iter_shapes()}
        most = int(self.threshold(ctx, "overlap_max_per_slide"))
        findings = []
        for n in ctx.slide_numbers(deck):
            animated = playback.animated_shape_ids(deck.slides[n - 1])
            shapes = [st for st in ctx.layout.slide(n).values() if st.lines]
            slide_findings, built = [], []
            for i, a in enumerate(shapes):
                for b in shapes[i + 1:]:
                    hit = _first_overlap(a.lines, b.lines, tol)
                    if not hit:
                        continue
                    la, lb = hit
                    box = [min(la.left, lb.left), min(la.top, lb.top), max(la.right, lb.right), max(la.bottom, lb.bottom)]
                    if a.shape_id in animated or b.shape_id in animated:
                        built.append((a.shape_id, b.shape_id, box))   # shown at different times: not a collision
                        continue
                    # Report it on the box whose wrapped line caused it, so the fix starts there.
                    slide_findings.append(Finding(self.id, Status.RED,
                        f"Text of '{names.get((n, a.shape_id))}' collides with '{names.get((n, b.shape_id))}' "
                        f"(\"{' '.join(la.words)[:30]}\" over \"{' '.join(lb.words)[:30]}\").",
                        slide=n, shape_id=a.shape_id, shape_name=names.get((n, a.shape_id)),
                        subject=f"with {b.shape_id}",
                        evidence={"other_shape": b.shape_id, "lines": [_desc(la), _desc(lb)], "box_emu": box,
                                  "rule": "drawn lines overlap sideways and by more than a quarter of a line's height vertically"}))
            if len(slide_findings) > most:
                # Not a "nudge one box" problem: usually a swapped font or a pasted diagram. One finding,
                # no fix attempts (each costs a full search).
                boxes = [f.evidence["box_emu"] for f in slide_findings]
                slide_findings = [Finding(self.id, Status.RED,
                    f"Text collides in {len(boxes)} places on this slide. That's usually a font being swapped "
                    f"(see the font findings) or a pasted diagram; check it by hand.",
                    slide=n, subject="many",
                    evidence={"overlaps": len(boxes), "box_emu": _union(boxes),
                              "rule": f"more than {most} text-over-text collisions on one slide aren't fixed box by box"})]
            findings += slide_findings
            if built:
                cards = {sid for a, b, _ in built for sid in (a, b)}
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{len(cards)} animated text boxes overlap as the slide builds (they appear or disappear on "
                    f"clicks). Usually a deliberate build; check it in Slide Show.",
                    slide=n, subject="animated build",
                    evidence={"boxes": len(cards), "box_emu": _union([b for _, _, b in built]),
                              "rule": "overlapping text where a box (or its group) has an entrance or exit animation"}))
        return findings

    def fix(self, deck, finding, edits, ctx):
        if finding.subject in ("many", "animated build"):
            raise FixRefused("too many overlaps, or an animated build: not changed automatically")
        return self._separate(deck, finding, edits, ctx)

    def _separate(self, deck, finding, edits, ctx):
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
                                and (limit is None or t <= limit),
                            band=self.threshold(ctx, "fit_wrap_band_pct") / 100)
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


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]

