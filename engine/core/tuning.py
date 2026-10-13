"""Tuning (David 2026-10-11): every layout fix is described by a few numbers (what kind of fix, how big,
what triggered it, what kind of text), so David's 👍/👎 votes in the review can be matched to them and
`slidetistic tune` can propose rules. Approved rules live in `rules/tuning.yaml` as gates: a fix whose
description matches a gate is not made, and its finding stays open as "worth a look" ("fixed, or
untouched": a gate never half-applies a fix).

The same feature names are used in three places, so they must stay stable: the gate check here (planned
fix), the review bundle (the net change David actually sees, `visual.plan`), and `engine/tune.py`.
No slide text is ever recorded, only numbers and categories.
"""
from __future__ import annotations

import hashlib
import json
import math

from . import rules
from .geometry import EMU_PER_INCH

EMU_PER_PT = 12700
FIX_KINDS = ("move", "resize", "spacing", "font", "push", "pair", "other")


def gates() -> list[dict]:
    return list(rules.load("tuning").get("gates") or [])


def gates_hash() -> str:
    """Identifies the rule set a vote was cast under (votes on old rules can still be replayed)."""
    return hashlib.sha1(json.dumps(gates(), sort_keys=True, default=str).encode()).hexdigest()[:10]


def matches(gate: dict, features: dict) -> bool:
    """A gate matches when every condition holds. `check` / `fix`: a value or a list of values;
    `when`: feature → value, list of values, or {min, max} (inclusive). A missing feature never matches."""
    for key in ("check", "fix"):
        if key in gate:
            want = gate[key] if isinstance(gate[key], list) else [gate[key]]
            if features.get(key) not in want:
                return False
    for name, cond in (gate.get("when") or {}).items():
        value = features.get(name)
        if value is None:
            return False
        if isinstance(cond, dict):
            if "min" in cond and not value >= cond["min"]:
                return False
            if "max" in cond and not value <= cond["max"]:
                return False
        elif isinstance(cond, list):
            if value not in cond:
                return False
        elif value != cond:
            return False
    return True


def gate_for(features: dict, rule_set: list[dict] | None = None) -> dict | None:
    for g in gates() if rule_set is None else rule_set:
        if g.get("action", "skip") == "skip" and matches(g, features):
            return g
    return None


def fix_kind(*, font: float = 1.0, spacing: float = 1.0, width_pct: float = 0.0) -> str:
    """The most intrusive part of a fix, in David's order (box → spacing → font)."""
    if font < 1:
        return "font"
    if spacing < 1:
        return "spacing"
    if abs(width_pct) >= 0.5:
        return "resize"
    return "move"


def role(deck, sv, ctx=None) -> str:
    """title (title placeholder), header (the slide's largest short text), body (body placeholder), text."""
    shape = sv.shape
    if getattr(shape, "is_placeholder", False):
        try:
            kind = str(shape.placeholder_format.type).lower()
        except (AttributeError, ValueError):
            kind = ""
        if "title" in kind:
            return "title"
    layout = getattr(getattr(ctx, "layout", None), "slide", None)
    if layout is not None:
        from .fit import is_header
        try:
            if is_header(deck, sv, layout(sv.slide_number)):
                return "header"
        except Exception:  # noqa: BLE001 — a description must never stop a fix
            pass
    if getattr(shape, "is_placeholder", False):
        return "body"
    return "text"


def text_facts(sv) -> dict:
    from .content import shape_text
    from .fit import RUN_PROPS
    facts = {"words": len(shape_text(sv.shape).split())}
    if getattr(sv.shape, "has_text_frame", False):
        sizes = [int(el.get("sz")) for el in sv.shape.text_frame._txBody.iter(*RUN_PROPS) if el.get("sz")]
        facts["font_pt"] = round(max(sizes) / 100, 1) if sizes else None
    return facts


def trigger(deck, finding, ctx) -> dict:
    """How bad the problem was, in numbers, per check (from the finding's own evidence)."""
    if finding is None:
        return {}
    ev = finding.evidence or {}
    out = {"severity": finding.status.value, "problem": finding.subject}
    box = ev.get("box_emu")
    if finding.check_id == "L008" and box:
        l, t, r, b = box
        W, H = deck.slide_width, deck.slide_height
        pct = (getattr(ctx, "thresholds", None) or {}).get("safe_zone_pct", 5)
        mx, my = W * pct / 100, H * pct / 100
        past_border = max(mx - l, my - t, r - (W - mx), b - (H - my), 0)
        past_edge = max(-l, -t, r - W, b - H, 0)
        out["past_border_in"] = round(past_border / EMU_PER_INCH, 3)
        out["past_edge_in"] = round(past_edge / EMU_PER_INCH, 3)
    elif finding.check_id == "L009":
        out["orphan_words"] = len(str(ev.get("word", "")).split())
        out["lines"] = ev.get("lines")
    elif finding.check_id == "L010" and box:
        l, t, r, b = box
        out["overlap_pt"] = round(min(r - l, b - t) / EMU_PER_PT, 1)
    elif finding.check_id == "L001":
        if ev.get("lines") is not None and ev.get("original_lines") is not None:
            out["extra_lines"] = ev["lines"] - ev["original_lines"]
    elif finding.check_id == "L011":
        out["picture_share"] = ev.get("share")
    return out


def placement(deck, sv, finding=None, ctx=None) -> dict:
    """Where the text sits (David 2026-10-12): on a filled shape? in the header/footer band? how big?"""
    from . import fit
    th = getattr(ctx, "thresholds", None) or {}
    box = (finding.evidence or {}).get("box_emu") if finding is not None else None
    if box is None and sv.bounds is not None:
        box = (sv.bounds.left, sv.bounds.top, sv.bounds.right, sv.bounds.bottom)
    try:
        on = fit.backing_shape(deck, sv, th.get("on_shape_min_overlap_pct", 80) / 100) is not None
    except Exception:  # noqa: BLE001 — a description must never stop a fix
        on = None
    return {"on_shape": on, "band": fit.edge_band(deck, sv, box, th.get("header_footer_band_pct", 15)) or "none",
            "area_pct": round(fit.area_pct(deck, sv), 1)}


def describe_plan(deck, sv, plan, finding=None, ctx=None, check_id=None) -> dict:
    """Features of a planned fit fix (before anything is edited)."""
    b = sv.bounds
    dx, dy = plan.left - b.left, plan.top - b.top
    width_pct = (plan.width / b.width - 1) * 100 if b.width else 0.0
    f = {
        "check": check_id or (finding.check_id if finding else None),
        "fix": fix_kind(font=plan.font, spacing=plan.spacing, width_pct=width_pct),
        "move_in": round(math.hypot(dx, dy) / EMU_PER_INCH, 3),
        "width_pct": round(width_pct, 1),
        "font_pct": round((1 - plan.font) * 100, 1),
        "spacing_pct": round((1 - plan.spacing) * 100, 1),
        "role": role(deck, sv, ctx),
        "in_group": sv.xf.scale_x != 1 or sv.xf.off_x != 0 or sv.xf.off_y != 0,
        **text_facts(sv),
        **placement(deck, sv, finding, ctx),
        **trigger(deck, finding, ctx),
    }
    return f


def describe_push(deck, other, dy, finding=None, ctx=None, check_id=None) -> dict:
    """L008's stacked-title move: the text BELOW is pushed down to make room."""
    return {"check": check_id or (finding.check_id if finding else None), "fix": "push",
            "move_in": round(abs(dy) / EMU_PER_INCH, 3), "width_pct": 0.0, "font_pct": 0.0, "spacing_pct": 0.0,
            "role": role(deck, other, ctx), "in_group": False, **text_facts(other), **placement(deck, other, None, ctx),
            **trigger(deck, finding, ctx)}


def describe_pair(deck, sv, dx, dy, finding=None, ctx=None, check_id=None) -> dict:
    """L008 moving text together with the shape it sits on."""
    return {"check": check_id or (finding.check_id if finding else None), "fix": "pair",
            "move_in": round(math.hypot(dx, dy) / EMU_PER_INCH, 3), "width_pct": 0.0, "font_pct": 0.0,
            "spacing_pct": 0.0, "role": role(deck, sv, ctx), "in_group": False, **text_facts(sv),
            **placement(deck, sv, finding, ctx), **trigger(deck, finding, ctx)}


def allow(edits, sv, features: dict) -> None:
    """Record a planned fix; raise FixRefused if an approved tuning gate says not to make it."""
    from .edits import FixRefused
    gate = gate_for(features)
    note = {"slide": sv.slide_number, "shape_id": sv.shape_id, "features": features,
            "gate": gate.get("id") if gate else None}
    edits.notes.append(note)
    if gate:
        raise FixRefused(f"left as it was: {gate.get('why') or 'a tuning rule says this change is not worth making'}"
                         f" (tuning {gate.get('id', '?')})")
