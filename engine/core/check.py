from __future__ import annotations

from dataclasses import dataclass, field

GROUPS = ["fonts", "geometry", "layout", "playback", "media", "content", "other"]
GROUP_LETTERS = {"F": "fonts", "G": "geometry", "L": "layout", "P": "playback", "M": "media", "C": "content", "X": "other"}
SOURCES = {"canva", "google", "keynote", "any"}


@dataclass
class Context:
    thresholds: dict = field(default_factory=dict)
    preset: str = "any"
    crew_fonts: set[str] = field(default_factory=set)   # casefolded; fonts installed on show machines
    layout: object = None   # LayoutProvider, phase 4


class Check:
    id: str = ""
    title: str = ""
    group: str = ""
    description: str = ""
    default_check: bool = True
    default_fix: bool = False
    sources: list[str] = ["any"]
    requires: list[str] = []
    runs_after: list[str] = []
    thresholds: list[str] = []      # keys this check reads from rules/thresholds.yaml
    report_only: bool = False       # True = no fix() exists; the UI disables the Fix toggle
    version: int = 1

    def detect(self, deck, ctx: Context) -> list:
        raise NotImplementedError

    def fix(self, deck, finding, edits, ctx: Context) -> None:
        raise NotImplementedError

    def threshold(self, ctx: Context, key: str):
        if key not in self.thresholds:
            raise KeyError(f"{self.id} reads threshold '{key}' without declaring it in `thresholds`")
        return ctx.thresholds[key]

    @classmethod
    def metadata(cls) -> dict:
        return {
            "id": cls.id, "title": cls.title, "group": cls.group, "description": cls.description,
            "default_check": cls.default_check, "default_fix": cls.default_fix and not cls.report_only,
            "report_only": cls.report_only, "sources": cls.sources, "requires": cls.requires,
            "runs_after": cls.runs_after, "version": cls.version,
        }
