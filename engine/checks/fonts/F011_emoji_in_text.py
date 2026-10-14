import re

from engine.core import Check, Finding, Status
from engine.core import content

# Emoji blocks; the older symbols Unicode draws as emoji by default (Emoji_Presentation in U+2xxx: ✅ ⌚ ⭐ ☕,
# adversarial round 1); keycaps (1️⃣); and a symbol forced to emoji style by U+FE0F. A stray U+FE0F after a letter
# or digit (copy-paste debris, "Room 1️") draws as the plain character: not an emoji.
_BMP_EMOJI = ("\u231A\u231B\u23E9-\u23EC\u23F0\u23F3\u25FD\u25FE\u2614\u2615\u2648-\u2653\u267F\u2693\u26A1"
              "\u26AA\u26AB\u26BD\u26BE\u26C4\u26C5\u26CE\u26D4\u26EA\u26F2\u26F3\u26F5\u26FA\u26FD\u2705"
              "\u270A\u270B\u2728\u274C\u274E\u2753-\u2755\u2757\u2795-\u2797\u27B0\u27BF\u2B1B\u2B1C\u2B50\u2B55")
EMOJI = re.compile(f"[\U0001F000-\U0001FAFF{_BMP_EMOJI}]|[0-9#*]\uFE0F?\u20E3|[^\\w\\s]\uFE0F")


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
