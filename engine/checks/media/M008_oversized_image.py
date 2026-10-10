from engine.core import Check, Finding, Status
from engine.core import images


class OversizedImage(Check):
    id = "M008"
    title = "Oversized image"
    group = "media"
    description = "Images with far more pixels than they're shown at. They bloat the file and slow loading."
    report_only = True
    sources = ["any"]
    thresholds = ["output_width_px", "oversize_ratio", "oversize_min_mb"]

    def detect(self, deck, ctx):
        findings = []
        for pic in images.pictures(deck, self.threshold(ctx, "output_width_px")):
            if pic.ratio is None or pic.mb < self.threshold(ctx, "oversize_min_mb"):
                continue
            if pic.ratio >= self.threshold(ctx, "oversize_ratio"):
                findings.append(Finding(self.id, Status.YELLOW,
                    f"Image is {pic.px_w}×{pic.px_h} px ({pic.mb:.1f} MB) but shows about {pic.shown_px} px wide. "
                    f"A smaller copy would load faster.",
                    slide=pic.sv.slide_number, shape_id=pic.sv.shape_id, shape_name=pic.sv.name, subject="oversized",
                    evidence={"px": [pic.px_w, pic.px_h], "shown_px": pic.shown_px, "mb": round(pic.mb, 1),
                              "rule": f"{pic.ratio:.1f}× more pixels than shown (limit {self.threshold(ctx, 'oversize_ratio')}×) "
                                      f"and ≥{self.threshold(ctx, 'oversize_min_mb')} MB"}))
        return findings
