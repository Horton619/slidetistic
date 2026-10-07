"""Test-only check whose detect always raises. Proves one broken check never stops a run."""
from engine.core import Check


class DummyCrashes(Check):
    id = "X998"
    title = "Dummy: always crashes"
    group = "other"
    description = "Test-only."
    report_only = True

    def detect(self, deck, ctx):
        raise RuntimeError("boom")
