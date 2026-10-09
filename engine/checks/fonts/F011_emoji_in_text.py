import re

from engine.core import Check, Finding, Status
from engine.core import content

# Emoji blocks, plus any symbol forced to emoji style by the U+FE0F selector.
EMOJI = re.compile("[\U0001F000-\U0001FAFF]|.️")


class EmojiInText(Check):
    id = "F011"
    title = "Emoji in text"
    group = "fonts"
    description = "Emoji look different on Mac and Windows, and some show as empty boxes on older show machines."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        findings = []
        for n, slide in enumerate(deck.slides, 1):
            for shape in slide.shapes:
                found = EMOJI.findall(content.shape_text(shape))
                if found:
                    shown = "".join(dict.fromkeys(found))[:12]
                    findings.append(Finding(self.id, Status.YELLOW,
                        f"Text uses emoji ({shown}). Check how they look on the show machine.",
                        slide=n, shape_id=shape.shape_id, shape_name=shape.name, subject="emoji",
                        evidence={"emoji": shown, "count": len(found)}))
        return findings
