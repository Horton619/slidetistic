from engine.core import Check, Finding, FixRefused, Status, inches
from engine.core import fit, tuning
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
    thresholds = ["fit_wrap_band_pct", "safe_zone_pct", "overlap_min_pt", "fit_max_font_shrink_pct", "fit_min_line_spacing_pct", "body_widen_max_pct",
                  "header_footer_band_pct", "safe_zone_fix_min_area_pct", "on_shape_min_overlap_pct"]

    def detect(self, deck, ctx):
        if ctx.layout is None:
            return []
        W, H = deck.slide_width, deck.slide_height
        pct = self.threshold(ctx, "safe_zone_pct")
        mx, my = W * pct / 100, H * pct / 100
        views = {(sv.slide_number, sv.shape_id): sv for sv in deck.iter_shapes()}
        names = {k: sv.name for k, sv in views.items()}
        band_pct = self.threshold(ctx, "header_footer_band_pct")
        min_area = self.threshold(ctx, "safe_zone_fix_min_area_pct")
        findings = []
        for n in ctx.slide_numbers(deck):
            for sid, st in ctx.layout.slide(n).items():
                if not st.bounds:
                    continue
                l, t, r, b = st.bounds
                off = {"left": -l, "top": -t, "right": r - W, "bottom": b - H}
                border = {"left": mx - l, "top": my - t, "right": r - (W - mx), "bottom": b - (H - my)}
                rule = (f"text drawn at x {inches(l)}–{inches(r)} in, y {inches(t)}–{inches(b)} in; slide "
                        f"{inches(W)}×{inches(H)} in; safe border {pct}% = {inches(mx)} in sides, {inches(my)} in top/bottom")
                gone = [e for e, v in off.items() if v > 0]
                if gone:
                    # The line box crossing an edge isn't letters being cut off: a box holds the font's whole
                    # ascent ("Questions?" in a script font: box 0.26 in past the top, letters 0.8 in below it).
                    # Ask the picture; keep the edge only if letters touch it (or there's no picture).
                    gone = [e for e in gone if _cut_off(ctx.layout, n, st, e) is not False]
                # Words PowerPoint didn't draw at all. Mac PowerPoint leaves text past the slide edge out of the
                # PDF, so the drawn lines can end right at the edge while the rest of the sentence is gone
                # (adversarial round 2: a wrap-off line "fixed" by a 1 in move; 6 of 12 lines below the slide
                # reported as a safe-border yellow). Counted only when the drawn text reaches an edge.
                lost, lost_edges = _undrawn(deck, views.get((n, sid)), st)
                gone += [e for e in lost_edges if e not in gone]
                near = [e for e, v in border.items() if v > 0]
                if gone:
                    words = f" {lost} word{'s' if lost != 1 else ''} aren't drawn at all." if lost else ""
                    if lost:
                        rule += f"; {lost} of the box's words are missing from PowerPoint's drawing, which reaches the {'/'.join(lost_edges)} edge"
                    findings.append(Finding(self.id, Status.RED,
                        f"Text runs off the {' and '.join(gone)} of the slide as PowerPoint draws it.{words}",
                        slide=n, shape_id=sid, shape_name=names.get((n, sid)), subject="off-slide",
                        evidence={"edges": gone, "rule": rule, "box_emu": [l, t, r, b], "undrawn_words": lost}))
                elif near and fit.edge_band(deck, views.get((n, sid)), st.bounds, band_pct):
                    continue        # header/footer text sits by the edge on purpose (David 2026-10-12)
                elif near:
                    ev = {"edges": near, "rule": rule, "box_emu": [l, t, r, b]}
                    if fit.area_pct(deck, views.get((n, sid))) < min_area:
                        ev["note"] = True   # small text by an edge: left as designed, low priority (David 2026-10-12)
                    findings.append(Finding(self.id, Status.YELLOW,
                        f"Text reaches into the {pct}% safe border at the {' and '.join(near)} "
                        f"(by up to {inches(max(border[e] for e in near))} in).",
                        slide=n, shape_id=sid, shape_name=names.get((n, sid)), subject="safe-zone",
                        evidence=ev))
        return findings


    def fix(self, deck, finding, edits, ctx):
        """Cheapest change, box → line spacing → font, whose PREDICTED text sits fully inside the safe
        zone, on no other text, on no new picture, with no new single-word lines and (for headers) no
        extra line. Then the stacked-title move: push the text below down to make room."""
        sv = deck.find_shape(finding.slide, finding.shape_id)
        st = ctx.layout.measure(finding.slide, finding.shape_id)
        if not sv or not st or not st.lines or sv.rotation:
            raise FixRefused("can't measure this text")
        # David 2026-10-12 (and his votes): header/footer text is placed on purpose; small text near an edge is
        # left as designed (only big blocks are pulled in); text on a shape moves with the shape or not at all.
        if fit.edge_band(deck, sv, st.bounds, self.threshold(ctx, "header_footer_band_pct")):
            raise FixRefused("header/footer text is placed on purpose, so it isn't moved; check it by hand")
        min_area = self.threshold(ctx, "safe_zone_fix_min_area_pct")
        if finding.status == Status.YELLOW and fit.area_pct(deck, sv) < min_area:
            raise FixRefused(f"small text near the edge is left as designed (its box covers "
                             f"{fit.area_pct(deck, sv):.0f}% of the slide; blocks over {min_area}% are pulled in)")
        backing = fit.backing_shape(deck, sv, self.threshold(ctx, "on_shape_min_overlap_pct") / 100)
        if backing is not None:
            return self._move_with_shape(deck, finding, edits, ctx, sv, st, backing)
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
                            accept=lambda o, t: o <= orphans_now and (limit is None or t <= limit),
                            band=self.threshold(ctx, "fit_wrap_band_pct") / 100)
        if plan and fit.apply(edits, sv, plan, "fit the safe zone", finding, ctx):
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
                    tuning.allow(edits, other, tuning.describe_push(deck, other, dy, finding, ctx, self.id))
                    fit.place(edits, other, top=other.bounds.top + dy)
                    return
        raise FixRefused("no move, line spacing or font size (within the caps) gets this text inside the safe "
                         "zone without landing on other text or a picture; adjust it by hand")

    def _move_with_shape(self, deck, finding, edits, ctx, sv, st, backing):
        """Move the text and the shape it sits on by the same amount, so the drawn text ends up inside the safe
        zone and the shape stays on the slide, landing on no other text or new picture. Otherwise leave both."""
        W, H = deck.slide_width, deck.slide_height
        sl, stop, sr, sb = fit.safe_rect(deck, self.threshold(ctx, "safe_zone_pct"))
        l, t, r, b = st.bounds
        if r - l > sr - sl or b - t > sb - stop:
            raise FixRefused("the text is wider or taller than the safe zone; it sits on a shape, so it isn't resized")
        pad = W * 0.002
        dx = sl + pad - l if l < sl else (sr - pad - r if r > sr else 0.0)
        dy = stop + pad - t if t < stop else (sb - pad - b if b > sb else 0.0)
        ob = backing.bounds
        if ob.left + dx < 0 or ob.top + dy < 0 or ob.right + dx > W or ob.bottom + dy > H:
            raise FixRefused(f"the text sits on a shape ({backing.name}) that would leave the slide if both moved; "
                             "adjust them by hand")
        layout = ctx.layout.slide(finding.slide)
        tol = self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT
        moved = fit.shifted(st.lines, dx, dy)
        others = {k: v for k, v in layout.items() if k != backing.shape_id}
        mine = (ob.left, ob.top, ob.right, ob.bottom)
        new_obstacles = [x for x in fit.obstacles(deck, finding.slide, sv.shape_id, st.lines) if x != mine]
        if fit.collision(others, sv.shape_id, moved, tol) is not None or any(
                fit.hits_box(x, box, tol) for x in moved for box in new_obstacles):
            raise FixRefused(f"moving the text with its shape ({backing.name}) would land on other text or a picture")
        tuning.allow(edits, sv, tuning.describe_pair(deck, sv, dx, dy, finding, ctx, self.id))
        fit.place(edits, sv, left=sv.bounds.left + dx, top=sv.bounds.top + dy)
        fit.place(edits, backing, left=ob.left + dx, top=ob.top + dy)


def _undrawn(deck, sv, st) -> tuple[int, list[str]]:
    """(words of the box PowerPoint didn't draw, the edges its drawn text reaches) when both are non-zero."""
    if sv is None or not st.lines:
        return 0, []
    from engine.core.content import shape_text
    from engine.core.layout.pdf import _tokens
    lost = len(_tokens(shape_text(sv.shape))) - sum(len(l.tokens) for l in st.lines)
    if lost <= 0:
        return 0, []
    W, H = deck.slide_width, deck.slide_height
    l, t, r, b = st.bounds
    line_h = max(l_.bottom - l_.top for l_ in st.lines)
    # Mac leaves out whole words, so the drawn text stops up to a word short of the edge: about two line heights
    # for big text (48 pt words are ~1 in wide; adversarial G001 stopped 0.7 in short).
    side = max(228600, 2 * line_h)
    edges = [e for e, hit in (("right", r >= W - side), ("left", l <= side), ("bottom", b >= H - 1.5 * line_h),
                              ("top", t <= 1.5 * line_h)) if hit]
    return (lost, edges) if edges else (0, [])


def _cut_off(layout, n, st, edge):
    """True/False from the rendered picture for the line nearest that edge; None when there's no picture."""
    check = getattr(layout, "cut_off", None)
    if check is None or not st.lines:
        return None
    pick = {"top": min(st.lines, key=lambda l: l.top), "bottom": max(st.lines, key=lambda l: l.bottom),
            "left": min(st.lines, key=lambda l: l.left), "right": max(st.lines, key=lambda l: l.right)}[edge]
    results = [check(n, l, edge) for l in st.lines if l is pick or
               (edge in ("left", "right") and (l.left < 0 if edge == "left" else l.right > layout.deck.slide_width))]
    if any(r is True for r in results):
        return True
    return False if results and all(r is False for r in results) else None

