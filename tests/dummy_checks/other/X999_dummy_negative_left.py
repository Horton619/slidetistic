"""Test-only check: flags text shapes with a negative left edge and moves them to x=0.

Exists so the contract and runner tests exercise detect + fix before any real check exists.
"""
from engine.core import Check, Finding, Status, inches


class DummyNegativeLeft(Check):
    id = "X999"
    title = "Dummy: text left of slide"
    group = "other"
    description = "Test-only."
    default_fix = True

    def detect(self, deck, ctx):
        return [
            Finding(self.id, Status.RED, f"Box starts at x = {inches(sv.bounds.left)} in.",
                    slide=sv.slide_number, shape_id=sv.shape_id, shape_name=sv.name,
                    evidence={"left_in": inches(sv.bounds.left)})
            for sv in deck.iter_shapes()
            if sv.text_bearing and sv.group_depth == 0 and sv.bounds and sv.bounds.left < 0
        ]

    def fix(self, deck, finding, edits, ctx):
        edits.set_geometry(deck.find_shape(finding.slide, finding.shape_id), left=0)
