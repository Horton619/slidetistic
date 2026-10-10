from engine.core import EMU_PER_INCH, Check, Finding, Status, inches
from engine.core.layout.pdf import drawn_text
from engine.core.text_geometry import text_overhang


class TextBelowSlide(Check):
    id = "G002"
    title = "Text below the slide"
    group = "geometry"
    description = ("Text running past the bottom edge. With PowerPoint available it only reports words that are "
                   "actually cut off; extra box height alone is ignored.")
    report_only = True
    sources = ["any"]
    thresholds = ["offslide_tolerance_in"]

    def detect(self, deck, ctx):
        tol = self.threshold(ctx, "offslide_tolerance_in") * EMU_PER_INCH
        H = deck.slide_height
        findings = []
        for sv in deck.iter_shapes():
            if not sv.text_bearing or sv.bounds is None or sv.rotation:
                continue
            if text_overhang(sv.shape, sv.bounds, deck.slide_width, H)["bottom"] <= tol:
                continue
            over = sv.bounds.bottom - H
            drawn = drawn_text(ctx.layout, deck, sv, tol)
            if drawn is not None and drawn.total:
                # David 2026-10-10: box overhangs flagged far too often; only the words matter.
                if not drawn.missing and "bottom" not in drawn.off_edges:
                    continue
                msg = (f"{drawn.missing} of {drawn.total} words are below the bottom of the slide."
                       if drawn.missing else "The last line of text is drawn past the bottom of the slide.")
                findings.append(Finding(self.id, Status.RED, msg,
                    slide=sv.slide_number, shape_id=sv.shape_id, shape_name=sv.name, subject="off-slide",
                    evidence={"overhang_in": inches(over), "words_drawn": drawn.drawn, "words_total": drawn.total,
                              "rule": f"PowerPoint render: {drawn.drawn} of {drawn.total} words drawn"
                                      + (f", drawn text ends {inches(drawn.bounds[3])} in down a {inches(H)} in slide"
                                         if drawn.bounds else "")
                                      + "; words outside the slide are left out of the render."}))
                continue
            findings.append(Finding(self.id, Status.YELLOW,
                f"Text box runs {inches(over)} in below the slide. Check the last line of text is visible.",
                slide=sv.slide_number, shape_id=sv.shape_id, shape_name=sv.name, subject="below",
                evidence={"overhang_in": inches(over),
                          "rule": "box bottom minus its inner bottom margin is below the slide; "
                                  "whether any words are there needs PowerPoint's render"}))
        return findings
