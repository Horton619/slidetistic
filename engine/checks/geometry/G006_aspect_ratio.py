from engine.core import Check, Finding, Status, inches


class AspectRatio(Check):
    id = "G006"
    title = "Slide shape doesn't match the screen"
    group = "geometry"
    description = "Deck isn't 16:9 (or the target set in Settings). It will show with black bars or be cropped."
    report_only = True
    sources = ["any"]
    thresholds = ["target_aspect", "aspect_tolerance_pct"]

    def detect(self, deck, ctx):
        w, h = deck.slide_width, deck.slide_height
        if not h:
            return []
        ratio, target = w / h, self.threshold(ctx, "target_aspect")
        if abs(ratio - target) / target * 100 <= self.threshold(ctx, "aspect_tolerance_pct"):
            return []
        return [Finding(self.id, Status.YELLOW,
            f"Slides are {inches(w)} × {inches(h)} in ({_name(ratio)}); the screen is {_name(target)}. "
            f"Expect black bars unless the deck is reformatted.",
            subject="aspect", evidence={"ratio": round(ratio, 3), "target": target})]


def _name(r: float) -> str:
    for label, v in (("16:9", 16 / 9), ("16:10", 1.6), ("4:3", 4 / 3), ("1:1", 1.0), ("21:9", 21 / 9)):
        if abs(r - v) < 0.01:
            return label
    return f"{r:.2f}:1"
