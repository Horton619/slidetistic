from pathlib import Path

from engine.core import Check, Finding, Status
from engine.core import content
from engine.core.media import media_items


class LinkedMediaMissing(Check):
    id = "M003"
    title = "Linked media file"
    group = "media"
    description = "Video or audio stored outside the deck. It plays only if that file travels with the deck."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        findings = []
        for m in media_items(deck):
            if not m.linked or content.media_kind(m.target) and m.target.startswith("http"):
                continue    # embedded, or web video (M005)
            local = Path(m.target.removeprefix("file://").removeprefix("file:"))
            here = deck.path.parent / local.name
            if not local.is_absolute() and (deck.path.parent / local).exists() or here.exists():
                status, msg = Status.YELLOW, f"{m.kind.capitalize()} is linked to {local.name}, which is next to the deck. Copy both together, or embed it."
            else:
                status, msg = Status.RED, f"{m.kind.capitalize()} is linked to {m.target}, which isn't with the deck. Get the file and embed it."
            findings.append(Finding(self.id, status, msg, slide=m.slide, shape_id=m.shape_id,
                                    shape_name=m.shape_name, subject=m.target, evidence={"target": m.target}))
        return findings
