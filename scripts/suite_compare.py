"""Compare two suite runs (usually one Mac, one PC) and write a markdown report into <suite>/_compare/.

    venv/<bin|Scripts>/python scripts/suite_compare.py "<suite>/_runs/<runA>" "<suite>/_runs/<runB>" [--allow-mismatch]

Decks are matched by SHA-256, not path. Data-only findings (fonts, media, playback, content, box-based
geometry) and media details must match exactly: a difference is a platform bug. Findings that depend on
how PowerPoint drew the deck (L checks, drawn-word G001/G002) are shown side by side. See
docs/CROSS_PLATFORM_COMPARE.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

MEDIA_FIELDS = ("kind", "duration", "trimmed", "starts", "loop", "full_screen", "hidden", "volume", "storage",
                "format", "codec", "resolution", "mb", "risk")      # engine/export.py INVENTORY_COLUMNS


def engine_unchanged(a: str, b: str) -> bool:
    """True when two commits differ only outside the engine (docs, scripts, app): results are comparable."""
    import subprocess
    repo = Path(__file__).resolve().parent.parent
    try:
        r = subprocess.run(["git", "diff", "--quiet", a, b, "--", "engine", "requirements.txt"], cwd=repo, timeout=30)
        return r.returncode == 0
    except OSError:
        return False


def load(run_dir: Path) -> tuple[dict, dict[str, dict]]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    decks = {}
    for f in sorted((run_dir / "decks").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("sha256"):
            decks[d["sha256"]] = d
    return run, decks


def render_based(check: str, layout: bool) -> bool:
    return check.startswith("L") or (layout and check in ("G001", "G002"))


def split(rows: list, layout: bool) -> tuple[set, list]:
    exact = {tuple(r) for r in rows if not render_based(r[0], layout)}
    drawn = [r for r in rows if render_based(r[0], layout)]
    return exact, drawn


def counts(rows: list) -> Counter:
    return Counter(f"{r[0]} {r[1]}" for r in rows)


def media_key(row: dict) -> tuple:
    return (row.get("slide"), row.get("media"))


def fmt_row(r) -> str:
    check, status, slide, shape, subject = r
    where = f"slide {slide}" if slide else "deck"
    return f"`{check}` {status} · {where}{f' · shape {shape}' if shape else ''} · {subject}"


def secs(d: dict, step: str) -> str:
    s = d.get(step, {})
    return "—" if not s else ("TIMEOUT" if s.get("timed_out") else f"{s.get('seconds', 0):.0f}s")


PIXEL_DIFF = 40          # grey levels: JPEG noise and anti-aliasing stay under it
VISUAL_MIN_PCT = 0.5     # share of a slide's pixels that must change to be listed


def visual_diff(a_dir: Path, b_dir: Path, both: list[str], da: dict, out_dir: Path, A: str, B: str) -> list[str]:
    """Runs made with --images: the same slide picture from each side, pixel by pixel (review 2026-10-13, 3.5).
    Lists slides that look different and writes a side-by-side (A | B | changed pixels in red) for each."""
    from PIL import Image, ImageChops
    rows = []
    for h in both:
        key = h[:12]
        ia, ib = a_dir / "images" / key, b_dir / "images" / key
        if not ia.is_dir() or not ib.is_dir():
            continue
        for fa in sorted(ia.glob("*.jpg")):
            fb = ib / fa.name
            if not fb.exists():
                continue
            ga, gb = Image.open(fa).convert("L"), Image.open(fb).convert("L")
            if gb.size != ga.size:
                gb = gb.resize(ga.size)
            mask = ImageChops.difference(ga, gb).point(lambda v: 255 if v > PIXEL_DIFF else 0)
            pct = 100 * mask.histogram()[255] / (ga.size[0] * ga.size[1])
            if pct >= VISUAL_MIN_PCT:
                rows.append((pct, da[h]["deck"], fa.name, fa, fb, mask))
    if not rows:
        return ["", "## Rendered slides", "", "No slide picture differs by more than "
                f"{VISUAL_MIN_PCT}% of its pixels." if any((a_dir / "images").glob("*")) and any((b_dir / "images").glob("*"))
                else "_Not compared: run both sides with --images._"]
    rows.sort(key=lambda r: -r[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["", "## Rendered slides", "", f"Slides whose pictures differ by {VISUAL_MIN_PCT}%+ of their pixels "
             f"(left {A}, middle {B}, right: changed pixels).", "", "| Deck | Picture | Changed | Side by side |",
             "| --- | --- | --- | --- |"]
    for i, (pct, deck, name, fa, fb, mask) in enumerate(rows):
        link = ""
        if i < 40:
            a, b = Image.open(fa).convert("RGB"), Image.open(fb).convert("RGB").resize(Image.open(fa).size)
            red = Image.new("RGB", a.size, (255, 60, 60))
            marked = Image.composite(red, a.point(lambda v: v // 3), mask)
            sheet = Image.new("RGB", (a.size[0] * 3 + 20, a.size[1]), (20, 20, 30))
            for j, im in enumerate((a, b, marked)):
                sheet.paste(im, (j * (a.size[0] + 10), 0))
            fname = f"{i + 1:02d}-{Path(deck).stem[:40]}-{name}".replace(" ", "_")
            sheet.save(out_dir / fname, quality=80)
            link = f"[view]({out_dir.name}/{fname})"
        lines.append(f"| {deck} | {name} | {pct:.1f}% | {link} |")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_a")
    ap.add_argument("run_b")
    ap.add_argument("--allow-mismatch", action="store_true", help="compare runs from different commits")
    args = ap.parse_args()
    a_dir, b_dir = Path(args.run_a), Path(args.run_b)
    (ra, da), (rb, db) = load(a_dir), load(b_dir)
    ca, cb = ra["commit"].split("+")[0], rb["commit"].split("+")[0]
    same_engine = ca == cb or engine_unchanged(ca, cb)
    if not same_engine and not args.allow_mismatch:
        sys.exit(f"Different engine code ({ca} vs {cb}): pull the same commit on both, or pass --allow-mismatch")
    layout = ra.get("layout") and rb.get("layout")
    A, B = ra["platform"], rb["platform"]
    if A == B:
        A, B = f"{A} ({ra['run'][:13]})", f"{B} ({rb['run'][:13]})"

    out = [f"# {ra['run']}  vs  {rb['run']}", ""]
    if ca != cb:
        out += [f"_Commits differ ({ca} vs {cb}); "
                + ("engine code is identical, so results are comparable._" if same_engine
                   else "engine code DIFFERS (compared with --allow-mismatch)._"), ""]
    out += [f"| | {A} | {B} |", "| --- | --- | --- |"]
    for k in ("commit", "dirty", "layout", "os", "python", "powerpoint", "poppler", "ffprobe", "started", "finished"):
        out.append(f"| {k} | {ra.get(k, '')} | {rb.get(k, '')} |")
    out.append(f"| renderer | {ra['renderer']['name']} ({'on' if ra['renderer']['available'] else ra['renderer']['why']}) "
               f"| {rb['renderer']['name']} ({'on' if rb['renderer']['available'] else rb['renderer']['why']}) |")
    if not layout:
        out += ["", "_At least one run is without PowerPoint: L checks and drawn-word G001/G002 aren't compared._"]

    both = sorted(set(da) & set(db), key=lambda h: da[h]["deck"])
    only_a = sorted(set(da) - set(db), key=lambda h: da[h]["deck"])
    only_b = sorted(set(db) - set(da), key=lambda h: db[h]["deck"])
    paths_b = {d["deck"].lower(): h for h, d in db.items()}

    summary, sections, bugs = [], [], 0
    for h in both:
        a, b = da[h], db[h]
        problems, notes = [], []
        for side, d in ((A, a), (B, b)):
            for step in ("scan", "repair"):
                s = d.get(step, {})
                other = (b if d is a else a).get(step, {})
                if (s.get("exit") not in (0, None) and not s.get("timed_out")
                        and (s.get("exit"), s.get("warnings")) == (other.get("exit"), other.get("warnings"))):
                    if d is a:      # the same refusal on both sides (e.g. a .key file): expected, say it once
                        notes.append(f"{step}: both refused it: {(s.get('warnings') or [''])[0]}")
                    continue
                if s.get("timed_out"):
                    problems.append(f"**{side}: {step} timed out** after {s.get('seconds')}s")
                elif s.get("exit") not in (0, None):
                    problems.append(f"**{side}: {step} exit {s.get('exit')}** {s.get('warnings', [])[:1]} {s.get('stderr', '')[-200:]}")
                if (s.get("summary") or {}).get("tool_error"):
                    problems.append(f"**{side}: {s['summary']['tool_error']} crashed check(s) in {step}**")
            if d.get("second_repair_changes"):
                msg = f"{side}: second repair still changed {d['second_repair_changes']} things"
                listed = d.get("second_repair_list") or []
                if listed:
                    msg += " (" + "; ".join(f"slide {c.get('slide')} {c.get('check_id')} {c.get('shape_name') or ''} "
                                            f"{c.get('prop')}" for c in listed[:5]) + ("…" if len(listed) > 5 else "") + ")"
                if layout:      # known open issue (docs/EDGE_CASES.md: layout fixes don't settle in one repair)
                    notes.append(msg + " (known open: layout fixes don't settle in one repair)")
                else:
                    problems.append(f"**{msg}**")
            other_w = (b if d is a else a).get("repair", {}).get("warnings", [])
            for w in d.get("repair", {}).get("warnings", []):
                if w not in other_w:        # the same warning on both sides isn't a difference
                    notes.append(f"{side} warning: {w}")
        for step in ("scan", "repair"):
            ea, ra_ = split(a.get(step, {}).get("findings", []), layout)
            eb, rb_ = split(b.get(step, {}).get("findings", []), layout)
            for r in sorted(ea - eb):
                problems.append(f"{step}: only {A}: {fmt_row(r)}")
            for r in sorted(eb - ea):
                problems.append(f"{step}: only {B}: {fmt_row(r)}")
            ca, cb = counts(ra_), counts(rb_)
            for k in sorted(set(ca) | set(cb)):
                if ca[k] != cb[k]:
                    notes.append(f"{step} (drawn by PowerPoint): `{k}` {A} {ca[k]} · {B} {cb[k]}")
        ma = {media_key(r): r for r in a.get("media", {}).get("inventory", [])}
        mb = {media_key(r): r for r in b.get("media", {}).get("inventory", [])}
        for k in sorted(set(ma) | set(mb), key=str):
            if k not in ma or k not in mb:
                problems.append(f"media: {k} only on {A if k in ma else B}")
                continue
            diffs = [f"{f} {ma[k].get(f)!r}→{mb[k].get(f)!r}" for f in MEDIA_FIELDS if ma[k].get(f) != mb[k].get(f)]
            if diffs:
                problems.append(f"media slide {k[0]} {k[1]}: " + ", ".join(diffs))
        ca_, cb_ = len(a.get("repair", {}).get("changes", [])), len(b.get("repair", {}).get("changes", []))
        if ca_ != cb_:
            notes.append(f"changes made: {A} {ca_} · {B} {cb_}")
        bugs += bool(problems)
        differs = [n for n in notes if ": both refused it: " not in n]
        status = "**differs**" if problems else ("drawn differs" if differs else "same")
        summary.append(f"| {a['deck']} | {status} | {secs(a, 'repair')} | {secs(b, 'repair')} |")
        if problems or notes:
            sections += ["", f"### {a['deck']}", ""] + [f"- {p}" for p in problems] + [f"- _{n}_" for n in notes]
            ta, tb = a.get("repair", {}).get("stages", {}), b.get("repair", {}).get("stages", {})
            if ta or tb:
                sections.append(f"- _repair stages: {A} {ta} · {B} {tb}_")

    out += ["", f"**{len(both)} decks compared · {len(both) - bugs} with no exact-check differences · "
                f"{bugs} to look at · {len(only_a)} only in {A} · {len(only_b)} only in {B}**", ""]
    out += [f"| Deck | Result | {A} repair | {B} repair |", "| --- | --- | --- | --- |"] + summary
    if only_a or only_b:
        out += ["", "## Not compared"]
        for side, hs, src in ((A, only_a, da), (B, only_b, db)):
            for h in hs:
                d = src[h]
                twin = paths_b.get(d["deck"].lower()) if side == A else None
                why = "same path, different file (changed or not fully synced)" if twin else "not in the other run"
                out.append(f"- {side} only: {d['deck']} ({why})")
    out += ["", "## Differences"] + (sections or ["", "None."])
    dest = a_dir.parent.parent / "_compare" / f"{ra['run']}__{rb['run']}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out += visual_diff(a_dir, b_dir, both, da, dest.with_suffix(""), A, B)
    dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(dest)


if __name__ == "__main__":
    main()
