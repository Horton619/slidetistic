"""Finds every check by filename. Adding a check never means editing a list."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from .check import GROUPS, Check

CHECKS_DIR = Path(__file__).resolve().parent.parent / "checks"
FILE_RE = re.compile(r"^[A-Z][0-9]{3}_\w+\.py$")


def discover(extra_dirs: list[Path] = ()) -> list[type[Check]]:
    found: dict[str, type[Check]] = {}
    for root in [CHECKS_DIR, *extra_dirs]:
        for path in sorted(Path(root).rglob("*.py")):
            if not FILE_RE.match(path.name):
                continue
            for cls in _load_checks(path):
                if cls.id in found:
                    raise ValueError(f"Duplicate check id {cls.id}: {path}")
                found[cls.id] = cls
    return order(list(found.values()))


def order(checks: list[type[Check]]) -> list[type[Check]]:
    """Group order (fonts → geometry → layout → …), then id, with runs_after respected."""
    by_id = {c.id: c for c in checks}
    pending = sorted(checks, key=lambda c: (GROUPS.index(c.group) if c.group in GROUPS else 99, c.id))
    done: list[type[Check]] = []
    placed: set[str] = set()
    while pending:
        for c in pending:
            if all(dep in placed or dep not in by_id for dep in c.runs_after):
                done.append(c)
                placed.add(c.id)
                pending.remove(c)
                break
        else:
            raise ValueError("Circular runs_after among: " + ", ".join(c.id for c in pending))
    return done


def _load_checks(path: Path) -> list[type[Check]]:
    mod_name = f"_slidetistic_checks.{path.parent.name}.{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return [
        obj for obj in vars(module).values()
        if isinstance(obj, type) and issubclass(obj, Check) and obj is not Check and obj.__module__ == mod_name
    ]
