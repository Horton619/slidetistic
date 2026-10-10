from pathlib import Path

from engine.core import Check, Finding, Status
from engine.core import rules
from engine.core.media import media_items, probe


class MediaFormatRisk(Check):
    id = "M004"
    title = "Video format may not play"
    group = "media"
    description = "Formats that may not play on the other platform (WMV on Mac, HEVC on Windows…). MP4 with H.264 + AAC is safest."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        r = rules.load("media_formats")
        findings = []
        for m in media_items(deck):
            if m.linked:
                continue
            reasons = []
            ext = Path(m.target).suffix.lower().lstrip(".")
            if ext in r["extensions"]:
                reasons.append(r["extensions"][ext])
            p = probe(m) or {}
            for key, table in (("video_codec", "video_codecs"), ("audio_codec", "audio_codecs")):
                if (p.get(key) or "").lower() in r[table]:
                    reasons.append(r[table][p[key].lower()])
            if reasons:
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{m.kind.capitalize()} format: {'; '.join(dict.fromkeys(reasons))}. Convert to MP4 (H.264 + AAC) to be safe.",
                    slide=m.slide, shape_id=m.shape_id, shape_name=m.shape_name, subject=m.target,
                    evidence={"extension": ext, "video_codec": p.get("video_codec"), "audio_codec": p.get("audio_codec")}))
        return findings
