from engine.core import Check, Finding, FixRefused, Status, inches
from engine.core import fit
from engine.core.layout.pdf import EMU_PER_PT


class TextOutsideSafeZone(Check):
    id = "L008"
    title = "Text outside the safe zone"
    group = "layout"
    description = "Text (as PowerPoint draws it) inside the safe border at the screen edge, or off the slide entirely."
    default_fix = True          # David 2026-10-10: bring text inside the safe zone, don't just flag it
    requires = ["layout"]
    sources = ["any"]
    runs_after = ["L001", "L010", "L009", "G001"]
    thresholds = ["safe_zone_pct", "overlap_min_pt", "fit_max_font_shrink_pct", "fit_min_line_spacing_pct", "body_widen_max_pct"]

    def detect(self, deck, ctx):
        if ctx.layout is None:
            return []
        W, H = deck.slide_width, deck.slide_height
        pct = self.threshold(ctx, "safe_zone_pct")
        mx, my = W * pct / 100, H * pct / 100
        names = {(sv.slide_number, sv.shape_id): sv.name for sv in deck.iter_shapes()}
        findings = []
        for n in range(1, len(deck.slides) + 1):
            for sid, st in ctx.layout.slide(n).items():
                if not st.bounds:
                    continue
                l, t, r, b = st.bounds
                off = {"left": -l, "top": -t, "right": r - W, "bottom": b - H}
                border = {"left": mx - l, "top": my - t, "right": r - (W - mx), "bottom": b - (H - my)}
                rule = (f"text drawn at x {inches(l)}–{inches(r)} in, y {inches(t)}–{inches(b)} in; slide "
                        f"{inches(W)}×{inches(H)} in; safe border {pct}% = {inches(mx)} in sides, {inches(my)} in top/bottom")
                gone = [e for e, v in off.items() if v > 0]
                near = [e for e, v in border.items() if v > 0]
                if gone:
                    findings.append(Finding(self.id, Status.RED,
                        f"Text runs off the {' and '.join(gone)} of the slide as PowerPoint draws it.",
                        slide=n, shape_id=sid, shape_name=names.get((n, sid)), subject="off-slide",
                        evidence={"edges": gone, "rule": rule, "box_emu": [l, t, r, b]}))
                elif near:
                    findings.append(Finding(self.id, Status.YELLOW,
                        f"Text reaches into the {pct}% safe border at the {' and '.join(near)} "
                        f"(by up to {inches(max(border[e] for e in near))} in).",
                        slide=n, shape_id=sid, shape_name=names.get((n, sid)), subject="safe-zone",
                        evidence={"edges": near, "rule": rule, "box_emu": [l, t, r, b]}))
        return findings


    def fix(self, deck, finding, edits, ctx):
        """Cheapest change, box → line spacing → font, whose PREDICTED text sits fully inside the safe
        zone, on no other text, on no new picture, with no new single-word lines and (for headers) no
        extra line. Then the stacked-title move: push the text below down to make room."""
        sv = deck.find_shape(finding.slide, finding.shape_id)
        st = ctx.layout.measure(finding.slide, finding.shape_id)
        if not sv or not st or not st.lines or sv.rotation:
            raise FixRefused("can't measure this text")
        layout = ctx.layout.slide(finding.slide)
        safe = fit.safe_rect(deck, self.threshold(ctx, "safe_zone_pct"))
        tol = self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT
        obs = fit.obstacles(deck, finding.slide, sv.shape_id, st.lines)
        limit = fit.header_limit(deck, sv, layout, ctx)
        _, orphans_now, lines_now = fit.Reflow(sv, st).predict(sv.bounds.left, sv.bounds.width)
        fonts, spacings = fit.choices(ctx, self.threshold)
        widen = max(0, int(((safe[2] - safe[0]) / sv.bounds.width - 1) * 100))
        plan = fit.plan_fit(deck, sv, st, layout, safe, tol, move=True, obstacle_boxes=obs,
                            narrow_pct=15, widen_pct=widen, fonts=fonts, spacings=spacings,
                            accept=lambda o, t: o <= orphans_now and (limit is None or t <= limit))
        if plan and fit.apply(edits, sv, plan, "fit the safe zone"):
            return
        # Stacked title + body (PAT 2, 5, 23): push the text below down, if it has room, so the
        # title can follow next round.
        l, t, r, b = st.bounds
        sl, stop, sr, sb = safe
        if t < stop:
            dy = stop - t + deck.slide_width * 0.002
            moved = fit.shifted(st.lines, 0, dy)
            hit = fit.collision(layout, sv.shape_id, moved, tol)
            other, ost = (deck.find_shape(finding.slide, hit), layout.get(hit)) if hit else (None, None)
            if other and ost and ost.lines and not other.rotation:
                pushed = fit.shifted(ost.lines, 0, dy)
                others = {k: v for k, v in layout.items() if k != sv.shape_id}
                if (max(x.bottom for x in pushed) <= sb
                        and fit.collision(others, hit, pushed, tol) is None
                        and not any(fit.hits_box(x, box, tol) for x in pushed
                                    for box in fit.obstacles(deck, finding.slide, hit, ost.lines))):
                    fit.place(edits, other, top=other.bounds.top + dy)
                    return
        raise FixRefused("no move, line spacing or font size (within the caps) gets this text inside the safe "
                         "zone without landing on other text or a picture; adjust it by hand")
