from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """Cached: callers must not mutate the result."""
    path = RULES_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def names(name: str, key: str | None = None) -> set[str]:
    """A YAML list of font names (or a list under `key`) as a casefolded set."""
    data = load(name)
    return {str(n).casefold() for n in (data[key] if key else data)}
