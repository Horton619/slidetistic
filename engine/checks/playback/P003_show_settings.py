from pptx.oxml.ns import qn

from engine.core import Check, Finding, Status
from engine.core import playback


class ShowSettings(Check):
    id = "P003"
    title = "Unusual slide-show settings"
    group = "playback"
    description = "Kiosk mode, looping, window mode, 'show without animation', or only part of the deck set to show."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        _, _, show = playback.show_settings(deck)
        if show is None:
            return []
        found = []

        def add(status, subject, msg, **ev):
            found.append(Finding(self.id, status, msg, subject=subject, evidence=ev))

        if show.find(qn("p:kiosk")) is not None:
            add(Status.RED, "kiosk", "Deck is set to 'Browsed at a kiosk': clicks and the clicker won't advance slides, only timings and links.")
        if show.find(qn("p:browse")) is not None:
            add(Status.YELLOW, "window", "Deck is set to 'Browsed by an individual (window)': the show opens in a window, not full screen.")
        if show.get("loop") == "1":
            add(Status.YELLOW, "loop", "Deck loops until Esc. Fine for a walk-in loop; a talk will restart at the end.")
        if show.get("showAnimation") == "0":
            add(Status.RED, "no-animation", "'Show without animation' is on: builds won't play and animated videos may not start.")
        rng = show.find(qn("p:sldRg"))
        if rng is not None:
            add(Status.RED, "range", f"Only slides {rng.get('st')}–{rng.get('end')} are set to show; the rest will be skipped.",
                start=rng.get("st"), end=rng.get("end"))
        if show.find(qn("p:custShow")) is not None:
            add(Status.YELLOW, "custom-show", "Deck is set to play a custom show, not all slides.")
        if show.get("useTimings") == "0" and any(playback.advance_after_ms(s) for s in deck.slides):
            add(Status.YELLOW, "timings-off", "Slides have timings, but 'Use timings' is off, so they won't auto-advance. Intended?")
        return found
