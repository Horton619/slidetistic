from engine.core import Check, Finding, Status
from engine.core import fonts


class EmbedMacMayNotLoad(Check):
    id = "F008"
    title = "Embedded font licence forbids embedding"
    group = "fonts"
    description = "Embedded fonts whose licence says they must not be embedded. PowerPoint may ignore the copy; install the font instead."
    report_only = True
    sources = ["canva", "google", "any"]

    def detect(self, deck, ctx):
        findings = []
        for ef in fonts.embedded_fonts(deck):
            for s in ef.slots:
                if not s.info:
                    continue
                fam = fonts.alias(s.info.family)
                # Compression is NOT a warning sign: PowerPoint compresses every embed it saves
                # (corpus 2026-10-09: 101 of 101, Mac and Windows).
                if not s.info.fs_type & fonts.FSTYPE_RESTRICTED:
                    continue
                why = "has a licence flag that forbids embedding, so PowerPoint may ignore the copy"
                findings.append(Finding(self.id, Status.YELLOW,
                    f"{fam} ({s.slot}) {why}. Safest: install {fam} on the show machine.",
                    subject=f"{fam}/{s.slot}",
                    evidence={"compressed": s.info.compressed, "fs_type": s.info.fs_type}))
        return findings
