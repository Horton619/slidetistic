from engine.core import Check, Finding, Status
from engine.core import images

RISKY = {
    "image/webp": "WebP, which older PowerPoint versions can't show",
    "image/heic": "HEIC (iPhone photo format), which Windows PowerPoint may not show",
    "image/heif": "HEIF (iPhone photo format), which Windows PowerPoint may not show",
    "image/x-wmf": "a Windows vector graphic (WMF) that can draw differently on Mac",
    "image/x-emf": "a Windows vector graphic (EMF) that can draw differently on Mac",
}


class RiskyImageFormat(Check):
    id = "M011"
    title = "Risky image format"
    group = "media"
    description = "WebP, HEIC and WMF/EMF images that may not show, or show differently, on the other platform."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        findings = []
        for pic in images.pictures(deck, 1920):
            why = RISKY.get(pic.content_type)
            if why:
                findings.append(Finding(self.id, Status.YELLOW, f"Image is {why}. Check it on the show machine.",
                    slide=pic.sv.slide_number, shape_id=pic.sv.shape_id, shape_name=pic.sv.name,
                    subject=pic.content_type, evidence={"format": pic.content_type}))
        return findings
