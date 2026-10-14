from engine.core import Check, Finding, Status
from engine.core import content


class LinkedToLocalPath(Check):
    id = "X004"
    title = "Linked to someone's computer"
    group = "other"
    description = "Charts, media or links pointing at a file on the author's computer (C:\\…, /Users/…). It won't exist on the show machine."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        findings, seen = [], set()
        on_shapes = _media_shape_rids(deck)
        for rel in content.external_rels(deck):
            # Linked video/audio on a media shape is M003's (it knows whether the file sits next to the deck).
            # A sound with no shape (a transition or action sound) is nobody else's (adversarial round 1).
            if rel.reltype.rsplit("/", 1)[-1] in ("video", "audio", "media") and (id(rel.part), rel.r_id) in on_shapes:
                continue
            if not content.is_local_path(rel.target) or (rel.slide, rel.target) in seen:
                continue
            seen.add((rel.slide, rel.target))
            what = rel.reltype.rsplit("/", 1)[-1]
            where = f"slide {rel.slide}" if rel.slide else str(rel.part.partname)
            findings.append(Finding(self.id, Status.RED,
                f"A {what} link on {where} points at {rel.target}, a file on the author's computer. "
                f"Get the file and embed it.",
                slide=rel.slide, subject=rel.target, evidence={"target": rel.target, "type": what}))
        return findings


def _media_shape_rids(deck) -> set:
    """(part, relationship id) of every link a video or audio shape uses (a:videoFile, a:audioFile, p14:media)."""
    out = set()
    for slide in deck.slides:
        for el in slide._element.iter():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag in ("videoFile", "audioFile", "quickTimeFile", "media"):
                for k, v in el.attrib.items():
                    if k.endswith("}link") or k.endswith("}embed"):
                        out.add((id(slide.part), v))
    return out
