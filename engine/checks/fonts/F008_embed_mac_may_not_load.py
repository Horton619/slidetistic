from engine.core import Check, Finding, Status
from engine.core import fonts


class EmbedMacMayNotLoad(Check):
    id = "F008"
    title = "Embedded font Mac may not load"
    group = "fonts"
    description = "Embedded fonts stored compressed, or whose license forbids embedding. Install the font instead."
    report_only = True
    sources = ["canva", "google", "any"]

    def detect(self, deck, ctx):
        findings = []
        for ef in fonts.embedded_fonts(deck):
            for s in ef.slots:
                if not s.info:
                    continue
                fam = fonts.alias(s.info.family)
                if s.info.compressed:
                    why = "is stored in a compressed format Mac PowerPoint may not load"
                elif s.info.fs_type & fonts.FSTYPE_RESTRICTED:
                    why = "has a license flag that forbids embedding, so PowerPoint may ignore the copy"
                else:
                    continue
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} ({s.slot}) {why}. Safest: install {fam} on the show machine.",
                    subject=f"{fam}/{s.slot}",
                    evidence={"compressed": s.info.compressed, "fs_type": s.info.fs_type}))
        return findings
