from engine.core import EMU_PER_INCH, Check, Finding, Status, inches
from engine.core.text_geometry import text_overhang


class TextBelowSlide(Check):
    id = "G002"
    title = "Text box below the slide"
    group = "geometry"
    description = "Text boxes that run past the bottom edge. Often harmless extra box height; check the last line shows."
    report_only = True
    sources = ["any"]
    thresholds = ["offslide_tolerance_in"]

    def detect(self, deck, ctx):
        tol = self.threshold(ctx, "offslide_tolerance_in") * EMU_PER_INCH
        return [
            Finding(self.id, Status.YELLOW,
                    f"Text box runs {inches(sv.bounds.bottom - deck.slide_height)} in below the slide. "
                    f"Check the last line of text is visible.",
                    slide=sv.slide_number, shape_id=sv.shape_id, shape_name=sv.name, subject="below",
                    evidence={"overhang_in": inches(sv.bounds.bottom - deck.slide_height),
                              "rule": "box bottom minus its inner bottom margin is below the slide; "
                                      "whether any words are there needs the layout check (L008)"})
            for sv in deck.iter_shapes()
            if sv.text_bearing and sv.bounds is not None and not sv.rotation
            and text_overhang(sv.shape, sv.bounds, deck.slide_width, deck.slide_height)["bottom"] > tol
        ]
