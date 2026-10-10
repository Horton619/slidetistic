from engine.core import Check, Finding, Status, fonts, rules
from engine.core.shapes import PICTURE

CANVA_SIZE = (18288000, 10287000)     # 20 × 11.25 in (PAT MBD, Canva)
GOOGLE_SIZE = (9144000, 5143500)      # 10 × 5.625 in


class SourceFingerprint(Check):
    id = "X001"
    title = "Where the deck came from"
    group = "other"
    description = "Guesses the source app (Canva, Google Slides, Keynote, a PDF conversion, or PowerPoint) to pick sensible defaults."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        signals: dict[str, list[str]] = {"canva": [], "google": [], "keynote": [], "pdf": []}
        size = (deck.slide_width, deck.slide_height)
        shapes = deck.iter_shapes()
        if size == CANVA_SIZE:
            signals["canva"].append("20 × 11.25 in slides")
        aliases = set(rules.load("font_aliases"))
        typefaces = {r.typeface for r in fonts.font_refs(deck)}
        if typefaces & aliases or any(fonts.split_style(t) and fonts.split_style(t)[0] in aliases for t in typefaces):
            signals["canva"].append("Canva-only font names like 'Calibri (MS)'")
        if any(sv.name.startswith("Google Shape;") for sv in shapes):
            signals["google"].append("shapes named 'Google Shape;…'")
        if size == GOOGLE_SIZE:
            signals["google"].append("10 × 5.625 in slides")
        app = (deck.prs.core_properties.title or "", _app_name(deck))
        if "keynote" in app[1].lower():
            signals["keynote"].append(f"saved by {app[1]}")
        slides = deck.slides
        full_pics = sum(1 for n in range(1, len(slides) + 1)
                        if _one_full_picture(deck, [sv for sv in shapes if sv.slide_number == n]))
        if slides and full_pics / len(slides) >= 0.8:
            signals["pdf"].append(f"{full_pics} of {len(slides)} slides are a single full-slide picture")

        weight = {"canva": 2, "google": 2, "keynote": 3, "pdf": 3}
        best = max(signals, key=lambda k: (len(signals[k]) * weight[k], k == "google"))
        source = best if signals[best] else "powerpoint"
        label = {"canva": "a Canva export", "google": "a Google Slides export", "keynote": "a Keynote export",
                 "pdf": "a PDF converted to slides", "powerpoint": "made in PowerPoint"}[source]
        why = "; ".join(signals[best]) if signals[best] else "no export fingerprints found"
        return [Finding(self.id, Status.GREEN_CLEAN, f"Looks like {label} ({why}).", subject=source,
                        informational=True, evidence={"source": source, "signals": signals})]


def _app_name(deck) -> str:
    for part in deck.prs.part.package.iter_parts():
        if str(part.partname) == "/docProps/app.xml":
            import re
            m = re.search(rb"<Application>([^<]*)</Application>", part.blob)
            return m.group(1).decode("utf8", "replace") if m else ""
    return ""


def _one_full_picture(deck, svs) -> bool:
    top = [sv for sv in svs if sv.group_depth == 0]
    if len(top) != 1 or top[0].kind != PICTURE or top[0].bounds is None:
        return False
    b = top[0].bounds
    return b.width * b.height >= 0.9 * deck.slide_width * deck.slide_height
