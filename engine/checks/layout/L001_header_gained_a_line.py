from engine.core import Check, Finding, FixRefused, Status
from engine.core import fit
from engine.core.layout.pdf import EMU_PER_PT


class HeaderGainedALine(Check):
    id = "L001"
    title = "Header gained a line"
    group = "layout"
    description = "A header that now wraps to more lines than in the original deck (e.g. a font fix made it wider)."
    default_fix = True          # David 2026-10-10: 1 line → 2 in a header breaks the design
    requires = ["layout"]
    sources = ["any"]
    thresholds = ["safe_zone_pct", "overlap_min_pt", "fit_max_font_shrink_pct", "fit_min_line_spacing_pct",
                  "body_widen_max_pct"]

    def detect(self, deck, ctx):
        if ctx.layout is None or not ctx.baseline_lines:
            return []
        findings = []
        for n in range(1, len(deck.slides) + 1):
            layout = ctx.layout.slide(n)
            for sid, st in layout.items():
                sv = deck.find_shape(n, sid)
                was = ctx.baseline_lines.get((n, sid))
                if not sv or was is None or len(st.lines) <= was or not fit.is_header(deck, sv, layout):
                    continue
                findings.append(Finding(self.id, Status.RED,
                    f"Header now wraps to {len(st.lines)} lines; it was {was} in the original deck.",
                    slide=n, shape_id=sid, shape_name=sv.name, subject="header",
                    evidence={"lines": len(st.lines), "original_lines": was,
                              "box_emu": list(st.bounds) if st.bounds else None,
                              "rule": "the slide's largest, short (≤12 words) text is a header; its line count "
                                      "must not grow past the original deck's"}))
        return findings

    def fix(self, deck, finding, edits, ctx):
        layout = ctx.layout.slide(finding.slide)
        sv, st = deck.find_shape(finding.slide, finding.shape_id), layout.get(finding.shape_id)
        if not sv or not st or not st.lines or sv.rotation:
            raise FixRefused("can't measure this header")
        safe = fit.safe_rect(deck, self.threshold(ctx, "safe_zone_pct"))
        fonts, _ = fit.choices(ctx, self.threshold)
        was = finding.evidence["original_lines"]
        widen = max(0, int(((safe[2] - safe[0]) / sv.bounds.width - 1) * 100) + 1)
        plan = fit.plan_fit(deck, sv, st, layout, safe, self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT,
                            narrow_pct=0, widen_pct=widen, fonts=fonts,
                            obstacle_boxes=fit.obstacles(deck, finding.slide, sv.shape_id, st.lines),
                            accept=lambda o, t: t <= was)
        if not plan or not fit.apply(edits, sv, plan, f"keep the header on {was} line(s)"):
            raise FixRefused(f"can't get it back to {was} line(s) within the safe zone and the font cap")
