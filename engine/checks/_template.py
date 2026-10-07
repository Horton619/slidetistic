"""Copy to engine/checks/<group>/<ID>_<slug>.py (e.g. geometry/G005_text_hidden_behind_picture.py).

The registry finds it by filename; nothing else needs editing. Then write
tests/checks/test_<ID>_<slug>.py with a deck where it fires and one where it must not.
"""
from engine.core import Check, Finding, FixRefused, Status, inches


class TemplateCheck(Check):
    id = "X000"                  # next free id in the group; never reuse or renumber
    title = "Short name"
    group = "other"              # fonts | geometry | layout | playback | media | other
    description = "One plain line a crew member understands."
    default_check = True
    default_fix = False          # stays off until it passes the promotion rule (SPEC §8)
    report_only = False          # True if there is no fix
    sources = ["any"]            # presets that enable it by default: canva | google | keynote | any
    requires = []                # ["layout"] if it needs ctx.layout
    runs_after = []              # check ids that must run first
    thresholds = []              # keys read from rules/thresholds.yaml via self.threshold(ctx, key)
    version = 1

    def detect(self, deck, ctx):
        findings = []
        for sv in deck.iter_shapes():
            ...  # read only: never change the deck here
        return findings

    def fix(self, deck, finding, edits, ctx):
        sv = deck.find_shape(finding.slide, finding.shape_id)
        ...  # change it only through `edits`; raise FixRefused("plain reason") to decline
