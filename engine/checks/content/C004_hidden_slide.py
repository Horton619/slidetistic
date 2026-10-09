from engine.core import Check, Finding, Status
from engine.core import content


class HiddenSlide(Check):
    id = "C004"
    title = "Hidden slide"
    group = "content"
    description = "Slides marked hidden. They're skipped in the show; make sure that's intended."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        return [
            Finding(self.id, Status.YELLOW, "Slide is hidden and will be skipped in the show.",
                    slide=n, subject="hidden", evidence={"slide_name": content.slide_name(s, n)})
            for n, s in enumerate(deck.slides, 1) if content.is_hidden(s)
        ]
