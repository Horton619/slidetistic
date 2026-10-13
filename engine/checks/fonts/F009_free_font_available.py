from collections import defaultdict

from engine.core import Check, Finding, Status
from engine.core import fonts, fonts_catalog, fonts_install

LABEL = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
         700: "Bold", 800: "ExtraBold", 900: "Black"}


def label(weight: int, style: str) -> str:
    name = LABEL.get(weight, str(weight))
    return f"{name} Italic" if style == "italic" else name


class FreeFontAvailable(Check):
    id = "F009"
    title = "Missing font is a free download"
    group = "fonts"
    description = ("Fonts F007 reports as missing that are free to download (makers' own downloads such as "
                   "Microsoft Aptos, Fontsource, Google Fonts). Get fonts installs them for this user.")
    report_only = True          # the install is the Get fonts button, never part of a repair
    sources = ["canva", "google", "any"]
    runs_after = ["F001", "F002", "F003", "F004"]

    def detect(self, deck, ctx):
        """Informational: never counted with the problems (F007 already reports the font as missing).
        Reads only the cached catalog; never the network (design §3)."""
        missing = fonts.uncovered(deck, ctx)
        if not missing:
            return []
        if not fonts_catalog.available():
            return [Finding(self.id, Status.YELLOW, "Couldn't check for free fonts: the font list hasn't been "
                            "downloaded yet (it needs the internet once).", subject="catalog", informational=True,
                            evidence={"rule": "no cached Fontsource catalog"})]
        from engine.core.font_use import visible_fonts
        drawn = {fonts.normalized_family(v["family"]).casefold() for v in visible_fonts(deck).values()}
        missing = {f: refs for f, refs in missing.items()
                   if f.casefold() in drawn or any(r.typeface.casefold() in drawn for r in refs)}   # no text uses it: nothing to get
        if not missing:
            return []
        here = fonts_install.installed()["families"]
        by_base = defaultdict(lambda: {"refs": [], "weights": set(), "names": set()})
        for fam, refs in missing.items():
            suffix = fonts.flag_only_suffix(fam)
            base = fam[: -len(suffix)].strip() if suffix else fam
            entry = fonts_catalog.lookup(fam) or fonts_catalog.lookup(base)
            if entry is None:
                continue
            weight = 400 if fonts_catalog.lookup(fam) else fonts_install.weight_of(suffix)
            item = by_base[entry["family"]]
            item["entry"] = entry
            item["names"].add(fam)
            for r in refs:
                item["refs"].append((r, weight))
        findings = []
        for family, item in sorted(by_base.items()):
            if family.casefold() in here:
                continue        # already on this computer: nothing to download
            variants = sorted({v for r, w in item["refs"] for v in fonts_install.variants_for([r], w)})
            p = fonts_install.plan(family, variants)
            refs = [r for r, _ in item["refs"]]
            if not p["variants"]:
                continue
            got = ", ".join(label(w, s) for w, s in p["variants"])
            lacking = f" Not in this family: {', '.join(label(w, s) for w, s in p['unavailable'])}." if p["unavailable"] else ""
            whose = f"a free download from {p['publisher']}" if p.get("publisher") else "a free font"
            findings.append(Finding(self.id, Status.YELLOW,
                f"{family} is {whose}. Get fonts can install {got} ({fonts.where(refs)}).{lacking}",
                subject=family, informational=True,
                evidence={**fonts.usage_evidence(refs), "font_id": p["id"], "source": p.get("source") or p["type"],
                          "publisher": p.get("publisher"), "license": p.get("license"),
                          "variants": [list(v) for v in p["variants"]], "unavailable": [list(v) for v in p["unavailable"]],
                          "names": sorted(item["names"]),
                          "rule": "F007 family (or its base family without a weight word) found in the cached "
                                  "Fontsource catalog and not installed on this computer"}))
        return findings
