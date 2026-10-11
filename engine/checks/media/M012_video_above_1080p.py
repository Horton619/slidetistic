from engine.core import Check, Finding, Status
from engine.core.media import media_items, probe


class VideoAbove1080p(Check):
    id = "M012"
    title = "Video bigger than 1080p"
    group = "media"
    description = "4K and other videos above 1080p: re-encode them to 1080p before the show so show machines play them smoothly."
    report_only = True           # re-encoding happens outside SlideTistic for now (David 2026-10-11)
    sources = ["any"]
    thresholds = ["video_max_height_px"]

    def detect(self, deck, ctx):
        limit = int(self.threshold(ctx, "video_max_height_px"))
        findings = []
        for m in media_items(deck):
            p = probe(m) or {}
            w, h = p.get("width"), p.get("height")
            if m.kind != "video" or not h or min(w or h, h) <= limit:
                continue
            trimmed = bool(m.trim_start_ms or m.trim_end_ms)
            findings.append(Finding(self.id, Status.YELLOW,
                f"Video is {w}×{h}{' (4K)' if h >= 2000 or (w or 0) >= 3800 else ''}. Re-encode it to 1080p "
                f"(e.g. HandBrake) for smoother playback on show machines."
                + (" It's trimmed in PowerPoint, but the cut parts are still in the file: trim them in the re-encode too."
                   if trimmed else ""),
                slide=m.slide, shape_id=m.shape_id, shape_name=m.shape_name, subject=m.target,
                evidence={"px": [w, h], "mb": p.get("mb"), "trimmed": trimmed, "codec": p.get("video_codec"),
                          "rule": f"shorter side {min(w or h, h)} px > {limit} px"}))
        return findings
