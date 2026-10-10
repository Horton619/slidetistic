from pptx.oxml.ns import qn

from engine.core import Check, Finding, FixRefused, Status
from engine.core import content
from engine.core.media import media_items, probe, with_click_sequence_play

# Clicker-driven shows: "In click sequence" and "Automatically" both work. These don't.
WHY = {
    "on_click": "is set to 'When Clicked On': it only plays if someone clicks the video itself; the clicker won't start it",
    "no_timing": "has no start setting: it only plays if someone clicks its play button; the clicker won't start it",
    "unknown": "has a start setting SlideTistic can't read; check it in PowerPoint's Animation pane",
}


class VideoWontStartOnItsOwn(Check):
    id = "M001"
    title = "Video won't start from the clicker"
    group = "media"
    description = "Videos set to 'When Clicked On' (or with no start setting) that the clicker can't start. Fix: 'In Click Sequence'."
    default_fix = True       # David confirmed in PowerPoint 2026-10-10: converted videos show "In Click Sequence"
    sources = ["any"]
    thresholds = ["target_play_mode"]

    def detect(self, deck, ctx):
        findings = []
        for m in media_items(deck):
            if m.mode in ("automatic", "click_sequence") or (m.linked and content.media_kind(m.target)):
                continue    # fine for a clicker; web video is M005's
            findings.append(Finding(self.id, Status.RED if m.mode == "on_click" else Status.YELLOW,
                f"{m.kind.capitalize()} {WHY[m.mode]}. Set it to 'In Click Sequence'.",
                slide=m.slide, shape_id=m.shape_id, shape_name=m.shape_name, subject=m.kind,
                evidence={"mode": m.mode, "target": self.threshold(ctx, "target_play_mode"), "rule": {
                    "on_click": "no play step in the click sequence; only the click-the-video trigger "
                                "(PowerPoint's 'When Clicked On', seen in 8 corpus videos)",
                    "no_timing": "no play step anywhere in the slide's timing",
                    "unknown": "a media step PowerPoint uses that SlideTistic hasn't classified (e.g. play/pause toggle)",
                }[m.mode]}))
        return findings

    def fix(self, deck, finding, edits, ctx):
        m = next((m for m in media_items(deck) if m.slide == finding.slide and m.shape_id == finding.shape_id), None)
        if m is None or m.mode in ("automatic", "click_sequence"):
            return
        if m.mode != "on_click":
            raise FixRefused("only 'When Clicked On' videos are converted so far; set this one in PowerPoint")
        timing = m.slide_part._element.find(qn("p:timing"))
        dur = round((probe(m) or {}).get("duration_s") or 0) * 1000 or None
        edits.replace_element(m.slide_part, timing, with_click_sequence_play(timing, m.shape_id, dur),
                              prop="video start", before="When Clicked On", after="In Click Sequence")
