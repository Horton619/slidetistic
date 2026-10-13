"""The review bundle the app reads: review.json + slide images in one folder.

The app never parses HTML; everything it shows (summary, findings, changes, tiers, boxes, images,
media, checks) comes from here. Images are files next to review.json, referenced by name.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from . import __version__, export, visual
from .core.deck import replace_retrying


def write(result, checks, config, out_dir: Path, *, visuals=None, note: str = "", prefit: Path | None = None,
          pending: bool = False, converted_from: str | None = None) -> Path:
    """`pending`: findings are final but the slide pictures are still being drawn (the app shows the
    findings straight away and the pictures when the full bundle follows)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    findings = [f.to_dict() for f in result.findings]
    data = {
        "engine": __version__,
        "input": str(result.input_path),
        "output": str(result.output_path) if result.output_path else None,
        "prefit": str(prefit) if prefit and prefit.exists() else None,
        "summary": result.summary(),
        "input_mb": round(Path(result.input_path).stat().st_size / 1e6, 1),
        "output_mb": round(Path(result.output_path).stat().st_size / 1e6, 1) if result.output_path and Path(result.output_path).exists() else None,
        "source": next(({"kind": f.subject, "message": f.message} for f in result.findings if f.check_id == "X001"), None),
        "findings": findings,
        "changes": [c.to_dict() for c in result.changes],
        "visual_note": note,
        "visuals_pending": pending,
        "converted_from": converted_from,       # the .key file this deck was converted from
        "visuals": [dict(asdict(v), tier=v.tier, tier_label=visual.TIERS[v.tier]) for v in (visuals or [])],
        "kinds": visual.KIND_LABEL,
        "inventory": export.inventory_rows(result.findings),
        "downloads": export.download_rows(result.findings),
        "totals": export.totals(export.inventory_rows(result.findings)),
        "fonts": export.font_rows(result.output_path or result.input_path, result.findings, getattr(config, "crew_fonts", ())),
        "checks": [dict(c.metadata(), ran=config.check_on(c), fix_on=config.fix_on(c)) for c in checks],
        "tuning": _tuning_meta(result, config),
    }
    path = out_dir / "review.json"
    tmp = path.with_suffix(".partial")
    tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
    replace_retrying(tmp, path)        # Dropbox/Defender may briefly hold the new file
    return path


def _tuning_meta(result, config) -> dict:
    """What a 👍/👎 vote needs to be replayed later: which deck, which rules and thresholds it was made under."""
    from .core import rules, tuning
    keys = ("safe_zone_pct", "fit_min_line_spacing_pct", "fit_max_font_shrink_pct", "orphan_max_words",
            "orphan_min_paragraph_words", "overlap_min_pt", "body_widen_max_pct", "fit_wrap_band_pct")
    th = {**rules.load("thresholds"), **(getattr(config, "overrides", None) or {})}
    return {"deck_sha12": _sha12(Path(result.input_path)), "gates_hash": tuning.gates_hash(),
            "thresholds": {k: th.get(k) for k in keys},
            "skipped_by_gates": sum(1 for n in getattr(result, "notes", []) if n.get("gate"))}


_SHA: dict = {}


def _sha12(path: Path) -> str:
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _SHA:
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        _SHA[key] = h.hexdigest()[:12]
    return _SHA[key]
