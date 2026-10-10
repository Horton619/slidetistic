from engine.core import Check, Finding, Status
from engine.core import images


class LowResolutionImage(Check):
    id = "M009"
    title = "Low-resolution image"
    group = "media"
    description = "Images stretched beyond their pixels. They look soft or blocky on a 1920×1080 screen."
    report_only = True
    sources = ["any"]
    thresholds = ["output_width_px", "low_res_ratio", "low_res_min_shown_px"]

    def detect(self, deck, ctx):
        findings = []
        for pic in images.pictures(deck, self.threshold(ctx, "output_width_px")):
            if pic.ratio is not None and pic.ratio < self.threshold(ctx, "low_res_ratio") \
                    and pic.shown_px >= self.threshold(ctx, "low_res_min_shown_px"):
                findings.append(Finding(self.id, Status.YELLOW,
                    f"Image is {pic.px_w} px wide but fills about {pic.shown_px} px of the screen "
                    f"({1 / pic.ratio:.0%} stretch). It may look soft; ask for a bigger original.",
                    slide=pic.sv.slide_number, shape_id=pic.sv.shape_id, shape_name=pic.sv.name, subject="low-res",
                    evidence={"px": [pic.px_w, pic.px_h], "shown_px": pic.shown_px,
                              "rule": f"{pic.px_w} px (after crop) shown ≈{pic.shown_px} px on a "
                                      f"{self.threshold(ctx, 'output_width_px')} px screen = {1 / pic.ratio:.1f}× stretch; "
                                      f"flagged above {1 / self.threshold(ctx, 'low_res_ratio'):.1f}× when ≥"
                                      f"{self.threshold(ctx, 'low_res_min_shown_px')} px wide"}))
        return findings
