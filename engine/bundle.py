"""The review bundle the app reads: review.json + slide images in one folder.

The app never parses HTML; everything it shows (summary, findings, changes, tiers, boxes, images,
media, checks) comes from here. Images are files next to review.json, referenced by name.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import __version__, export, visual


def write(result, checks, config, out_dir: Path, *, visuals=None, note: str = "", prefit: Path | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    findings = [f.to_dict() for f in result.findings]
    data = {
        "engine": __version__,
        "input": str(result.input_path),
        "output": str(result.output_path) if result.output_path else None,
        "prefit": str(prefit) if prefit and prefit.exists() else None,
        "summary": result.summary(),
        "source": next(({"kind": f.subject, "message": f.message} for f in result.findings if f.check_id == "X001"), None),
        "findings": findings,
        "changes": [c.to_dict() for c in result.changes],
        "visual_note": note,
        "visuals": [dict(asdict(v), tier=v.tier, tier_label=visual.TIERS[v.tier]) for v in (visuals or [])],
        "kinds": visual.KIND_LABEL,
        "inventory": export.inventory_rows(result.findings),
        "downloads": export.download_rows(result.findings),
        "totals": export.totals(export.inventory_rows(result.findings)),
        "checks": [dict(c.metadata(), ran=config.check_on(c), fix_on=config.fix_on(c)) for c in checks],
    }
    path = out_dir / "review.json"
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
    tmp.replace(path)
    return path
