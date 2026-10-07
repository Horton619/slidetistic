from __future__ import annotations

from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def load(name: str) -> dict:
    path = RULES_DIR / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
