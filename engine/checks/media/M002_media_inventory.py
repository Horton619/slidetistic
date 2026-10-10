from engine.core import Check, Finding, Status
from engine.core import content
from engine.core.media import media_items, probe

MODE = {"automatic": "plays automatically", "click_sequence": "starts on click {clicks}",
        "no_timing": "no start setting", "on_click": "starts when clicked", "unknown": "start setting unknown"}


class MediaInventory(Check):
    id = "M002"
    title = "Media inventory"
    group = "media"
    description = "Every video and audio clip, slide by slide: length, how it starts, loop, volume, format."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        findings = []
        for m in media_items(deck):
            p = probe(m) or {}
            names = content.slide_name(deck.slides[m.slide - 1], m.slide)
            parts = [_clock(p.get("duration_s")), MODE[m.mode].format(clicks=m.clicks)]
            if m.trim_start_ms or m.trim_end_ms:
                parts.append("trimmed")
            parts += [label for label, on in (("loops", m.loop), ("full screen", m.full_screen),
                                              ("hidden when stopped", m.hidden_when_stopped)) if on]
            if m.muted or m.volume == 0:
                parts.append("MUTED (volume 0)")
            elif m.volume is not None:
                parts.append(f"{m.volume}% volume")
            parts.append("linked: " + m.target if m.linked else "embedded")
            findings.append(Finding(self.id, Status.GREEN_CLEAN,
                f"{m.kind.capitalize()}: " + " · ".join(x for x in parts if x),
                slide=m.slide, shape_id=m.shape_id, shape_name=m.shape_name, subject=m.kind, informational=True,
                evidence={"slide_name": names, "kind": m.kind, "file": m.target, "linked": m.linked,
                          "mode": m.mode, "clicks": m.clicks, "loop": m.loop, "full_screen": m.full_screen,
                          "hidden_when_stopped": m.hidden_when_stopped, "volume": 0 if m.muted else m.volume,
                          "trim_start_ms": m.trim_start_ms, "trim_end_ms": m.trim_end_ms, **p}))
        return findings


def _clock(seconds) -> str:
    if seconds is None:
        return ""
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"
