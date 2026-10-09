import re

from engine.core import Check, Finding, Status

BAD_CHARS = re.compile(r'[\\/:*?"<>|]|[\U0001F000-\U0001FAFF]')


class FileHygiene(Check):
    id = "X002"
    title = "File name or size trouble"
    group = "other"
    description = "Very large decks, and file names with emoji, slashes or extreme length that trip up playback machines."
    report_only = True
    sources = ["any"]
    thresholds = ["deck_size_warn_mb", "filename_max_chars"]

    def detect(self, deck, ctx):
        findings = []
        mb = deck.path.stat().st_size / 1_048_576
        if mb > self.threshold(ctx, "deck_size_warn_mb"):
            findings.append(Finding(self.id, Status.YELLOW,
                f"Deck is {mb:,.0f} MB. Allow extra time to copy it and check it opens quickly on the show machine.",
                subject="size", evidence={"mb": round(mb)}))
        name = deck.path.name
        bad = sorted(set(BAD_CHARS.findall(name)))
        if bad:
            findings.append(Finding(self.id, Status.YELLOW,
                f"File name contains {' '.join(bad)}, which some playback software and USB drives can't handle.",
                subject="name-chars", evidence={"chars": bad}))
        if len(name) > self.threshold(ctx, "filename_max_chars"):
            findings.append(Finding(self.id, Status.YELLOW,
                f"File name is {len(name)} characters; long paths can fail to open on Windows.",
                subject="name-length", evidence={"length": len(name)}))
        return findings
