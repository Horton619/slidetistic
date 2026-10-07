from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum


class Status(str, Enum):
    GREEN_CLEAN = "green_clean"
    GREEN_FIXED = "green_fixed"
    YELLOW = "yellow"
    RED = "red"
    TOOL_ERROR = "tool_error"


@dataclass
class Finding:
    check_id: str
    status: Status
    message: str
    slide: int | None = None          # 1-based, for humans
    shape_id: int | None = None
    shape_name: str | None = None
    # Distinguishes several findings on the same shape (e.g. one per font name).
    subject: str = ""
    evidence: dict = field(default_factory=dict)
    # Info-only findings (inventories, fingerprints) are never counted as problems.
    informational: bool = False

    @property
    def key(self) -> tuple:
        """Identity used to match a finding between the scan and the re-scan."""
        return (self.check_id, self.slide, self.shape_id, self.subject)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Change:
    check_id: str
    slide: int | None
    shape_id: int | None
    shape_name: str | None
    prop: str
    before: object
    after: object
    part: str | None = None           # e.g. /ppt/slideMasters/slideMaster1.xml for non-shape edits

    def to_dict(self) -> dict:
        return asdict(self)
