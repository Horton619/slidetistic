from pptx.oxml.ns import qn

from engine.core import Check, Finding, Status
from engine.core.content import owning_shape

OLE_URI = "http://schemas.openxmlformats.org/presentationml/2006/ole"
ACTIVEX = "application/vnd.ms-office.activeX+xml"
VBA = "application/vnd.ms-office.vbaProject"


class NeedsAnotherApp(Check):
    id = "X003"
    title = "Needs another app"
    group = "other"
    description = "Embedded Excel/Word objects, ActiveX controls or macros. They may not open or run on the show machine."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        findings = []
        for n, slide in enumerate(deck.slides, 1):
            for gd in slide.part._element.iter(qn("a:graphicData")):
                if gd.get("uri") == OLE_URI:
                    ole = next(gd.iter(qn("p:oleObj")), None)
                    prog = ole.get("progId", "an embedded object") if ole is not None else "an embedded object"
                    sid, name = owning_shape(gd)
                    findings.append(Finding(self.id, Status.YELLOW,
                        f"Contains {prog}. Double-clicking it needs that app; check it displays correctly.",
                        slide=n, shape_id=sid, shape_name=name, subject="ole", evidence={"prog_id": prog}))
            if any(not r.is_external and r.target_part.content_type == ACTIVEX for r in slide.part.rels.values()):
                findings.append(Finding(self.id, Status.YELLOW,
                    "Contains ActiveX controls. They don't work on Mac and are often blocked on Windows.",
                    slide=n, subject="activex"))
        if any(p.content_type == VBA for p in deck.prs.part.package.iter_parts()):
            findings.append(Finding(self.id, Status.YELLOW,
                "Deck contains macros. They're usually blocked on show machines; check nothing depends on them.",
                subject="macros"))
        return findings

