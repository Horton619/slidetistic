"""`slidetistic tune`: turn David's 👍/👎 votes on changed slides into proposed rules (David 2026-10-11).

Votes are written by the app (Settings › Diagnostics › Tuning mode) as JSON lines, one file per machine
(`votes-<machine>.jsonl`) so Dropbox never has two writers on one file. Each vote carries the numbers that
describe the slide's changes (core/tuning.py), never slide text.

Nothing changes on its own: `tune` reports, proposes gates (each replayed against every vote so far), and
asks about splits it can't settle. `tune --apply P2` writes an approved proposal into rules/tuning.yaml.
"""
from __future__ import annotations

import json
import os
import socket
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .core import rules, tuning

REASONS = {"not_worth": "Not worth it", "worse": "Made it worse", "wrong_fix": "Wrong kind of fix",
           "false_flag": "Shouldn't have flagged it"}
# Features a gate may use: known when the fix is planned (diff_pct is only known after rendering: report only).
NUMERIC = ("move_in", "width_pct", "font_pct", "spacing_pct", "words", "font_pt", "past_border_in",
           "past_edge_in", "orphan_words", "overlap_pt", "extra_lines", "area_pct")
CATEGORY = ("role", "severity", "in_group", "on_shape", "band")
MIN_DOWNS = 3          # a proposal must remove at least this many 👎
MIN_PRECISION = 0.75   # …and at least this share of the votes it touches must be 👎
UP_COST = 2.0          # losing a 👍 fix costs twice what avoiding a 👎 gains (stability first)


def feedback_dir(explicit: str | None = None) -> Path:
    """--votes, then $SLIDETISTIC_FEEDBACK, then the shared Dropbox suite's _feedback, then ~/.slidetistic."""
    if explicit:
        return Path(explicit).expanduser()
    if os.environ.get("SLIDETISTIC_FEEDBACK"):
        return Path(os.environ["SLIDETISTIC_FEEDBACK"]).expanduser()
    home = Path.home()
    for suite in (home / "Library/CloudStorage/Dropbox/SlideTistic Test Suite", home / "Dropbox/SlideTistic Test Suite"):
        if suite.is_dir():
            return suite / "_feedback"
    return home / ".slidetistic" / "feedback"


def load_votes(folder: Path) -> list[dict]:
    """Latest vote per (deck, slide, exact set of changes); a 'clear' removes it."""
    rows = []
    for f in sorted(folder.glob("votes-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue        # a half-synced last line
    latest: dict[tuple, dict] = {}
    for r in sorted(rows, key=lambda r: r.get("t", "")):
        latest[(r.get("deck_sha12"), r.get("slide"), r.get("tuning_sig"))] = r
    return [r for r in latest.values() if r.get("vote") in ("up", "down")]


def _changes(vote) -> list[dict]:
    return [c for c in vote.get("changes") or [] if isinstance(c, dict)]


def _group(c: dict) -> str:
    if c.get("check") is None:
        return "deck-wide fix"          # a font rename etc. touched the shape; no single check owns it
    return f"{c.get('check')} {c.get('fix')}"


# --- proposals ---------------------------------------------------------------------------------------

def replay(gate_set: list[dict], votes: list[dict]) -> dict:
    """What the votes say about a rule set: a slide whose every change is gated would not change at all."""
    out = Counter()
    for v in votes:
        ch = _changes(v)
        hit = [c for c in ch if c.get("fix") != "other" and tuning.gate_for(c, gate_set)]
        if not ch or not hit:
            out[f"kept_{v['vote']}"] += 1
        elif len(hit) == len(ch):
            out[f"removed_{v['vote']}"] += 1
        else:
            out[f"partly_{v['vote']}"] += 1
    return dict(out)


def _score(r: dict) -> float:
    return r.get("removed_down", 0) + 0.5 * r.get("partly_down", 0) - UP_COST * (
        r.get("removed_up", 0) + 0.5 * r.get("partly_up", 0))


def _candidates(votes: list[dict]):
    """Single-condition gates for each (check, fix) group seen in the votes, cut at observed values."""
    by_group: dict[tuple, list[dict]] = defaultdict(list)
    for v in votes:
        for c in _changes(v):
            if c.get("fix") not in (None, "other") and c.get("check"):
                by_group[(c["check"], c["fix"])].append(c)
    for (check, fix), cs in by_group.items():
        base = {"check": check, "fix": fix, "action": "skip"}
        yield dict(base)                                   # this kind of fix, always
        if any(c.get("severity") == "red" for c in cs):
            yield dict(base, when={"severity": "yellow"})  # …only where it was a "worth a look" problem
        for name in NUMERIC:
            values = sorted({c[name] for c in cs if isinstance(c.get(name), (int, float))})
            for x in values:
                yield dict(base, when={name: {"max": x}})
                yield dict(base, when={name: {"max": x}, "severity": "yellow"})
                yield dict(base, when={name: {"min": x}})
        for name in CATEGORY:
            for value in sorted({c.get(name) for c in cs if c.get(name) is not None}, key=str):
                yield dict(base, when={name: value})


def propose(votes: list[dict], current: list[dict], limit: int = 6) -> list[dict]:
    """Greedy: the best-scoring candidate, then the best one on top of it, and so on."""
    chosen: list[dict] = []
    base = replay(current, votes)
    seen = set()
    for _ in range(limit):
        best, best_r, best_s = None, None, 0.0
        now = replay(current + chosen, votes)
        for cand in _candidates(votes):
            key = json.dumps(cand, sort_keys=True)
            if key in seen:
                continue
            r = replay(current + chosen + [cand], votes)
            gain_down = r.get("removed_down", 0) - now.get("removed_down", 0)
            lost_up = r.get("removed_up", 0) - now.get("removed_up", 0)
            touched = gain_down + lost_up
            if gain_down < MIN_DOWNS or not touched or gain_down / touched < MIN_PRECISION:
                continue
            s = _score(r) - _score(now)
            # Prefer the narrower rule on ties (a threshold over "this kind of fix, always").
            s += 0.01 * len(cand.get("when") or {})
            if s > best_s:
                best, best_r, best_s = cand, r, s
        if best is None:
            break
        seen.add(json.dumps(best, sort_keys=True))
        reasons = Counter(v.get("reason") for v in votes if v["vote"] == "down" and any(
            tuning.matches(best, c) for c in _changes(v)))
        best = dict(best, votes={"before": now, "after": best_r,
                                 "down_reasons": {REASONS.get(k, "no reason"): n for k, n in reasons.items()}})
        chosen.append(best)
    for i, g in enumerate(chosen, 1):
        g["proposal"] = f"P{i}"
        g["why"] = _describe(g)
    _ = base
    return chosen


def _describe(g: dict) -> str:
    parts = [f"{g['check']} {g['fix']} fixes"]
    for name, cond in (g.get("when") or {}).items():
        if isinstance(cond, dict):
            if "max" in cond:
                parts.append(f"{name} ≤ {cond['max']}")
            if "min" in cond:
                parts.append(f"{name} ≥ {cond['min']}")
        else:
            parts.append(f"{name} = {cond}")
    return "skip " + ", ".join(parts)


# --- follow-up questions -----------------------------------------------------------------------------

def questions(votes: list[dict], rule_set: list[dict] | None = None) -> list[str]:
    """Groups David split on (≥4 votes, 25-75 % 👍): which numbers differ most between his 👍 and 👎.
    Changes the rules (in force + proposed) would skip are left out: those splits are already explained."""
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for v in votes:
        for c in _changes(v):
            if rule_set and c.get("fix") != "other" and tuning.gate_for(c, rule_set):
                continue
            groups[_group(c)].append((v["vote"], dict(c, diff_pct=v.get("diff_pct"))))
    out = []
    for name, items in sorted(groups.items()):
        ups = [c for vote, c in items if vote == "up"]
        downs = [c for vote, c in items if vote == "down"]
        if len(items) < 4 or not 0.25 <= len(ups) / len(items) <= 0.75:
            continue
        diffs = []
        for feat in NUMERIC + ("diff_pct",):
            a = [c[feat] for c in ups if isinstance(c.get(feat), (int, float))]
            b = [c[feat] for c in downs if isinstance(c.get(feat), (int, float))]
            if len(a) >= 2 and len(b) >= 2:
                ma, mb = sum(a) / len(a), sum(b) / len(b)
                spread = max(abs(ma), abs(mb), 1e-9)
                diffs.append((abs(ma - mb) / spread, feat, ma, mb))
        cats = []
        for feat in CATEGORY:
            ca, cb = Counter(c.get(feat) for c in ups), Counter(c.get(feat) for c in downs)
            if set(ca) != set(cb) or len(ca) > 1:
                cats.append(f"{feat}: 👍 {dict(ca)} vs 👎 {dict(cb)}")
        top = sorted(diffs, reverse=True)[:3]
        hint = "; ".join(f"{f} averages {ma:.2f} on 👍 vs {mb:.2f} on 👎" for _, f, ma, mb in top)
        out.append(f"You split on **{name}** ({len(ups)} 👍 / {len(downs)} 👎). {(hint + '.') if hint else 'No number separates them.'}"
                   + (f" ({'; '.join(cats)})" if cats else "")
                   + " What made the 👎 ones bad: the size of the change, the kind of text, or something the numbers "
                     "don't capture?")
    return out


# --- report ------------------------------------------------------------------------------------------

def report(votes: list[dict], proposals: list[dict], asks: list[str], folder: Path) -> str:
    ups = sum(1 for v in votes if v["vote"] == "up")
    lines = [f"# Tuning report ({datetime.now():%Y-%m-%d %H:%M})", "",
             f"Votes: **{len(votes)}** slides ({ups} 👍 / {len(votes) - ups} 👎, "
             f"{(100 * ups / len(votes)) if votes else 0:.0f}% approved). Folder: `{folder}`.", ""]
    if not votes:
        return "\n".join(lines + ["No votes yet: turn on Settings › Diagnostics › Tuning mode and vote in the review."])
    reasons = Counter(v.get("reason") for v in votes if v["vote"] == "down")
    lines += ["## 👎 reasons", ""] + [f"- {REASONS.get(k, 'no reason given')}: {n}" for k, n in reasons.most_common()] + [""]
    lines += ["## By kind of change", "", "| Change | 👍 | 👎 | approved | top 👎 reason | median move (in) | median visible change (%) |",
              "|---|---|---|---|---|---|---|"]
    groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for v in votes:
        for c in _changes(v):
            groups[_group(c)].append((v, c))
    for name, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        u = sum(1 for v, _ in items if v["vote"] == "up")
        d = len(items) - u
        why = Counter(v.get("reason") for v, _ in items if v["vote"] == "down").most_common(1)
        moves = sorted(c["move_in"] for _, c in items if isinstance(c.get("move_in"), (int, float)))
        diffs = sorted(v["diff_pct"] for v, _ in items if isinstance(v.get("diff_pct"), (int, float)))
        lines.append(f"| {name} | {u} | {d} | {100 * u / len(items):.0f}% | "
                     f"{REASONS.get(why[0][0], '—') if why else '—'} | "
                     f"{moves[len(moves) // 2] if moves else '—'} | {diffs[len(diffs) // 2] if diffs else '—'} |")
    tiny = [v for v in votes if isinstance(v.get("diff_pct"), (int, float)) and v["diff_pct"] < 0.5]
    if tiny:
        tu = sum(1 for v in tiny if v["vote"] == "up")
        lines += ["", f"Changes that altered under 0.5% of the slide's pixels: {len(tiny)} ({tu} 👍 / {len(tiny) - tu} 👎)."]
    current = tuning.gates()
    lines += ["", "## Proposed rules", ""]
    if not proposals:
        lines.append(f"None yet: a rule needs at least {MIN_DOWNS} 👎 it would avoid, and "
                     f"{MIN_PRECISION:.0%} of the votes it touches must be 👎.")
    base = replay(current, votes)
    for p in proposals:
        b, a = p["votes"]["before"], p["votes"]["after"]
        lines += [f"**{p['proposal']}: {p['why']}**",
                  f"- Avoids {a.get('removed_down', 0) - b.get('removed_down', 0)} 👎 slide(s); loses "
                  f"{a.get('removed_up', 0) - b.get('removed_up', 0)} 👍 slide(s); "
                  f"{a.get('partly_down', 0) + a.get('partly_up', 0)} slide(s) would keep only some of their changes.",
                  f"- 👎 reasons it covers: {p['votes']['down_reasons'] or '—'}",
                  f"- Apply: `slidetistic tune --apply {p['proposal']}`", ""]
    if proposals:
        final = replay(current + proposals, votes)
        kept_u, kept_d = final.get("kept_up", 0) + final.get("partly_up", 0), final.get("kept_down", 0) + final.get("partly_down", 0)
        was_u, was_d = base.get("kept_up", 0) + base.get("partly_up", 0), base.get("kept_down", 0) + base.get("partly_down", 0)
        pct = lambda u, d: f"{100 * u / (u + d):.0f}%" if u + d else "—"
        lines.append(f"With all of them: changed slides you'd approve go from {pct(was_u, was_d)} to {pct(kept_u, kept_d)} "
                     f"({was_u + was_d} → {kept_u + kept_d} slides changed).")
    if current:
        lines += ["", f"Rules already in force: {', '.join(g.get('id', '?') for g in current)}."]
    lines += ["", "## Questions for David", ""] + ([f"- {q}" for q in asks] or ["- None: no kind of change has a clear split yet."])
    return "\n".join(lines) + "\n"


def apply_proposal(folder: Path, pid: str) -> dict:
    """Append proposal `pid` (from the last report) to rules/tuning.yaml as the next T### gate."""
    saved = json.loads((folder / "proposals.json").read_text(encoding="utf-8"))
    prop = next((p for p in saved["proposals"] if p["proposal"] == pid), None)
    if prop is None:
        raise SystemExit(f"No proposal {pid} in the last report; run `slidetistic tune` first.")
    path = rules.RULES_DIR / "tuning.yaml"
    used = [int(g["id"][1:]) for g in tuning.gates() if str(g.get("id", "")).startswith("T") and g["id"][1:].isdigit()]
    gid = f"T{(max(used) + 1 if used else 1):03d}"
    b, a = prop["votes"]["before"], prop["votes"]["after"]
    gate = {"id": gid, "check": prop["check"], "fix": prop["fix"], **({"when": prop["when"]} if prop.get("when") else {}),
            "action": "skip", "why": prop["why"],
            "votes": f"avoids {a.get('removed_down', 0) - b.get('removed_down', 0)} 👎, loses "
                     f"{a.get('removed_up', 0) - b.get('removed_up', 0)} 👍 ({datetime.now():%Y-%m-%d}, "
                     f"{saved['votes']} votes)"}
    import yaml
    text = path.read_text(encoding="utf-8")
    block = yaml.safe_dump([gate], allow_unicode=True, sort_keys=False, default_flow_style=None)
    block = "".join("  " + ln + "\n" for ln in block.splitlines())
    if "\ngates: []" in text:
        text = text.replace("\ngates: []", "\ngates:\n" + block.rstrip("\n"))
    else:
        text = text.rstrip("\n") + "\n" + block
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    rules.load.cache_clear()
    return gate


def main(args) -> int:
    folder = feedback_dir(getattr(args, "votes", None))
    if getattr(args, "apply", None):
        gate = apply_proposal(folder, args.apply)
        print(f"Added {gate['id']} to {rules.RULES_DIR / 'tuning.yaml'}: {gate['why']}")
        return 0
    votes = load_votes(folder) if folder.is_dir() else []
    proposals = propose(votes, tuning.gates())
    asks = questions(votes, tuning.gates() + proposals)
    if folder.is_dir():
        (folder / "proposals.json").write_text(json.dumps(
            {"t": datetime.now().isoformat(timespec="seconds"), "machine": socket.gethostname(),
             "votes": len(votes), "proposals": proposals}, indent=1, default=str), encoding="utf-8")
    if getattr(args, "json", False):
        print(json.dumps({"votes": len(votes), "proposals": proposals, "questions": asks}, default=str))
    else:
        text = report(votes, proposals, asks, folder)
        if getattr(args, "out", None):
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"Report written to {args.out}")
        else:
            sys.stdout.write(text)
    return 0
