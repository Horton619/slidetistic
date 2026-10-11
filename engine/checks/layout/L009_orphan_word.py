from engine.core import Check, Finding, FixRefused, Status
from engine.core import fit
from engine.core.layout.pdf import EMU_PER_PT


class OrphanWord(Check):
    id = "L009"
    title = "Single word on the last line"
    group = "layout"
    description = "A paragraph whose last line holds a single word (as PowerPoint draws it), like 'whole.' alone."
    default_fix = True          # David 2026-10-10
    requires = ["layout"]
    sources = ["any"]
    runs_after = ["L001", "L010"]
    thresholds = ["fit_wrap_band_pct", "orphan_max_words", "orphan_min_paragraph_words"] + ["safe_zone_pct", "overlap_min_pt", "fit_max_font_shrink_pct", "fit_min_line_spacing_pct", "body_widen_max_pct"]

    def detect(self, deck, ctx):
        if ctx.layout is None:
            return []
        limit = self.threshold(ctx, "orphan_max_words")
        shortest = self.threshold(ctx, "orphan_min_paragraph_words")
        names = {(sv.slide_number, sv.shape_id): sv.name for sv in deck.iter_shapes()}
        findings = []
        for n in ctx.slide_numbers(deck):
            for sid, st in ctx.layout.slide(n).items():
                by_para: dict[int, list] = {}
                for line, p in zip(st.lines, st.paragraph_of_line):
                    by_para.setdefault(p, []).append(line)
                for p, lines in by_para.items():
                    last = lines[-1]
                    words = [w for w in last.words if any(ch.isalnum() for ch in w)]
                    # A web address can't wrap; alone on a line is the best it can do (PAT slide 29).
                    if any("://" in w or w.lower().startswith("www.") or "@" in w for w in words):
                        continue
                    if len(lines) >= 2 and lines[-2].words and ("/" in lines[-2].words[-1] or lines[-2].words[-1].endswith("-")):
                        continue    # tail of a web address/DOI broken across lines (PAT 29: "01508-3")
                    # David 2026-10-10 (CLARB 11): "Board of / Directors" and "… Council / Chair" are
                    # designed breaks in short titles and labels, not orphans.
                    para_words = sum(1 for l in lines for w in l.words if any(ch.isalnum() for ch in w))
                    if para_words < shortest:
                        continue
                    if len(lines) >= 2 and 0 < len(words) <= limit:
                        findings.append(Finding(self.id, Status.YELLOW,
                            f"'{' '.join(words)}' sits alone on the last line of a paragraph.",
                            slide=n, shape_id=sid, shape_name=names.get((n, sid)), subject=f"para{p}",
                            evidence={"word": " ".join(words), "lines": len(lines),
                                      "box_emu": [last.left, last.top, last.right, last.bottom],
                                      "rule": f"paragraph {p + 1} draws as {len(lines)} lines; last line has "
                                              f"{len(words)} word(s) (limit {limit})"}))
        return findings


    def fix(self, deck, finding, edits, ctx):
        """Smallest width change (−15 % … +body_widen_max_pct) whose predicted re-wrap has fewer single-word
        last lines, no extra lines, stays inside the safe zone, and lands on no text or picture."""
        sv = deck.find_shape(finding.slide, finding.shape_id)
        st = ctx.layout.measure(finding.slide, finding.shape_id)
        if not sv or not st or not st.lines or sv.rotation:
            raise FixRefused("can't measure this text")
        layout = ctx.layout.slide(finding.slide)
        _, orphans_now, lines_now = fit.Reflow(sv, st).predict(sv.bounds.left, sv.bounds.width)
        limit = fit.header_limit(deck, sv, layout, ctx)
        plan = fit.plan_fit(deck, sv, st, layout, fit.safe_rect(deck, self.threshold(ctx, "safe_zone_pct")),
                            self.threshold(ctx, "overlap_min_pt") * EMU_PER_PT,
                            obstacle_boxes=fit.obstacles(deck, finding.slide, sv.shape_id, st.lines),
                            narrow_pct=15, widen_pct=int(self.threshold(ctx, "body_widen_max_pct")),
                            accept=lambda o, t: o < max(1, orphans_now) and t <= lines_now
                            and (limit is None or t <= limit),
                            band=self.threshold(ctx, "fit_wrap_band_pct") / 100)
        if not plan or not fit.apply(edits, sv, plan, "remove a single-word line"):
            raise FixRefused("no box width from −15 % to +"
                             f"{self.threshold(ctx, 'body_widen_max_pct')} % fixes it without adding a line, "
                             "leaving the safe zone, or landing on other text or a picture")
