from engine.core import Check, Finding, Status


class RotatedText(Check):
    id = "G003"
    title = "Rotated or flipped text"
    group = "geometry"
    description = "Text that's rotated or flipped. Left out of automatic geometry fixes; check it by eye."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        return [
            Finding(self.id, Status.YELLOW,
                    ("Text is flipped" if sv.flipped else f"Text is rotated {round(sv.rotation)}°")
                    + ". SlideTistic won't move it automatically.",
                    slide=sv.slide_number, shape_id=sv.shape_id, shape_name=sv.name, subject="rotated",
                    evidence={"rotation": round(sv.rotation, 1), "flipped": sv.flipped})
            for sv in deck.iter_shapes() if sv.text_bearing and (sv.rotation or sv.flipped)
        ]
