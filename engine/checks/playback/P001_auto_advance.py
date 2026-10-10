from engine.core import Check, Finding, Status
from engine.core import playback


class AutoAdvance(Check):
    id = "P001"
    title = "Slides advance on a timer"
    group = "playback"
    description = "Slides set to move on by themselves after a time. Right for a walk-in loop; risky in a talk."
    default_fix = False      # walk-in loops do this on purpose
    sources = ["any"]

    def detect(self, deck, ctx):
        if not playback.uses_timings(deck):
            return []        # Slide Show ▸ Use Timings is off, so the timers never fire
        timed = {n: playback.advance_after_ms(s) for n, s in enumerate(deck.slides, 1)}
        timed = {n: ms for n, ms in timed.items() if ms is not None}
        if not timed:
            return []
        n_slides = len(deck.slides)
        secs = sorted({round(ms / 1000) for ms in timed.values()})
        clicks_off = sum(1 for n in timed if playback.click_advance_off(deck.slides[n - 1]))
        span = f"{secs[0]} s" if len(secs) == 1 else f"{secs[0]}–{secs[-1]} s"
        if len(timed) == n_slides and len(secs) == 1:
            msg = (f"Every slide advances by itself after {span}"
                   + (" and clicks are off" if clicks_off == n_slides else "")
                   + ". Looks like a walk-in loop; fine if that's the plan.")
        else:
            msg = (f"{len(timed)} of {n_slides} slides advance by themselves after {span} "
                   f"(slides {_ranges(sorted(timed))}). Often leftover rehearsal timings: a slide can move on mid-sentence.")
        return [Finding(self.id, Status.YELLOW, msg, subject="timings",
                        evidence={"slides": sorted(timed), "seconds": {str(n): round(ms / 1000, 1) for n, ms in timed.items()},
                                  "clicks_off": clicks_off})]

    def fix(self, deck, finding, edits, ctx):
        for n in finding.evidence["slides"]:
            slide = deck.slides[n - 1]
            for t in playback.transitions(slide):
                edits.set_part_attr(slide.part, t, "advTm", None, prop="advance after")
                edits.set_part_attr(slide.part, t, "advClick", None, prop="advance on click")


def _ranges(nums: list[int]) -> str:
    out, start = [], None
    for i, n in enumerate(nums):
        start = n if start is None else start
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(out)
