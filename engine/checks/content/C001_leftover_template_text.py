import re

from engine.core import Check, Finding, Status
from engine.core import content, rules


class LeftoverTemplateText(Check):
    id = "C001"
    title = "Leftover template text"
    group = "content"
    description = "Text like 'Click to add title', 'Lorem ipsum', '[Name]' or 'TBD' that was never replaced."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        r = rules.load("template_text")
        findings = []
        for n, slide in enumerate(deck.slides, 1):
            for shape in slide.shapes:
                # Empty placeholders show their prompt only while editing, never in the show.
                text = content.shape_text(shape)
                if not text.strip():
                    continue
                hit, status = _match(text, r)
                if hit:
                    findings.append(Finding(self.id, status,
                        f"'{hit}' looks like template text that was never replaced.",
                        slide=n, shape_id=shape.shape_id, shape_name=shape.name, subject=hit.lower(),
                        evidence={"text": " ".join(text.split())[:120]}))
        return findings


def _match(text: str, r: dict) -> tuple[str | None, Status]:
    low = text.lower()
    for phrase in r["red"]:
        if phrase in low:
            i = low.index(phrase)
            return text[i:i + len(phrase)], Status.RED
    for pattern in r["red_patterns"]:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(0), Status.RED
    for word in r["yellow_words"]:
        m = re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text, re.I)
        if m:
            return m.group(0), Status.YELLOW
    return None, Status.YELLOW
