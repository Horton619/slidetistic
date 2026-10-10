from engine.core import Check, Finding, Status
from engine.core import playback


class ClickAdvanceOff(Check):
    id = "P002"
    title = "Click won't advance"
    group = "playback"
    description = "Slides with 'advance on mouse click' off and no timer. A mouse click won't move on (a clicker/keyboard still does)."
    default_fix = False
    sources = ["any"]

    def detect(self, deck, ctx):
        findings = []
        for n, slide in enumerate(deck.slides, 1):
            if playback.click_advance_off(slide) and playback.advance_after_ms(slide) is None:
                findings.append(Finding(self.id, Status.YELLOW,
                    "Mouse-click advance is off and there's no timer. A mouse click won't move on; "
                    "a presentation clicker or keyboard still will.", slide=n, subject="advClick"))
        return findings

    def fix(self, deck, finding, edits, ctx):
        slide = deck.slides[finding.slide - 1]
        for t in playback.transitions(slide):
            edits.set_part_attr(slide.part, t, "advClick", None, prop="advance on click")
