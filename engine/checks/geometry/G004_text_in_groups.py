from engine.core import Check, Finding, Status
from engine.core.shapes import GROUP


class TextInGroups(Check):
    id = "G004"
    title = "Text inside groups"
    group = "geometry"
    description = "Grouped text. Reported for reference; automatic fixes inside groups come later."
    report_only = True
    sources = ["any"]

    def detect(self, deck, ctx):
        shapes = deck.iter_shapes()
        findings = []
        for g in (sv for sv in shapes if sv.kind == GROUP and sv.group_depth == 0):
            inside = [sv for sv in shapes if sv.slide_number == g.slide_number and sv.group_depth > 0
                      and sv.text_bearing and _within(sv.shape, g.shape)]
            if inside:
                findings.append(Finding(self.id, Status.GREEN_CLEAN,
                    f"Group holds {len(inside)} text box{'es' * (len(inside) != 1)}.",
                    slide=g.slide_number, shape_id=g.shape_id, shape_name=g.name, subject="group",
                    informational=True, evidence={"text_shapes": [sv.name for sv in inside]}))
        return findings


def _within(shape, group) -> bool:
    node = shape.element.getparent()
    while node is not None:
        if node is group.element:
            return True
        node = node.getparent()
    return False
