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
        for rel in content.external_rels(deck):
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
