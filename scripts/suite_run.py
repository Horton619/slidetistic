"""Run the shared test suite through this machine's engine and write the results into the suite folder,
so the Mac and the PC can be compared (docs/CROSS_PLATFORM_COMPARE.md).

    venv/<bin|Scripts>/python scripts/suite_run.py --suite "<Dropbox>/SlideTistic Test Suite" [--layout] [--images]

Every deck goes through `engine.cli` exactly as the app runs it (scan, repair, a second repair of the
result, media inventory), each step in its own process with a time limit, so one stuck deck can't stop
the run. Decks are only read; everything is written under <suite>/_runs/<run>/. Results quote client
text: they stay in the suite folder, never in git.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"_runs", "_compare", "_mailbox"}
DECK_EXT = {".pptx", ".pptm", ".ppt", ".key"}


def plat() -> str:
    return {"darwin": "mac", "win32": "win"}.get(sys.platform, sys.platform)


def git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30).stdout.strip()
    except OSError:
        return ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_decks(suite: Path, only: str | None) -> list[Path]:
    decks = []
    for p in sorted(suite.rglob("*")):
        rel = p.relative_to(suite)
        if (p.is_file() and p.suffix.lower() in DECK_EXT and not p.name.startswith(("~$", "._"))
                and " - mended" not in p.name and not SKIP_DIRS & set(rel.parts)
                and (only is None or rel.match(only))):
            decks.append(p)
    return decks


def tool_version(name: str, args: list[str]) -> str:
    from engine.core import tools
    exe = tools.find(name)
    if not exe:
        return "not found"
    try:
        out = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        return ((out.stdout or out.stderr).strip().splitlines() or ["?"])[0]
    except OSError as e:
        return f"error: {e}"


def powerpoint_version() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"PowerPoint.Application\CurVer") as k:
                cur = winreg.QueryValue(k, None)
            exe = Path(r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE")
            if exe.exists():
                import win32api
                info = win32api.GetFileVersionInfo(str(exe), "\\")
                ms, ls = info["FileVersionMS"], info["FileVersionLS"]
                return f"{cur} {ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            return cur
        except Exception as e:      # noqa: BLE001 — diagnostics only
            return f"unknown ({e})"
    plist = Path("/Applications/Microsoft PowerPoint.app/Contents/Info.plist")
    if plist.exists():
        import plistlib
        return plistlib.loads(plist.read_bytes()).get("CFBundleShortVersionString", "?")
    return "not installed"


def run_cli(args: list[str], timeout: float) -> dict:
    """One engine.cli call: its JSON-lines events, with each event's arrival time (s from start)."""
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, "-m", "engine.cli", *args], cwd=REPO, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    events, timed_out = [], False
    import threading
    err: list[str] = []
    threading.Thread(target=lambda: err.append(proc.stderr.read()), daemon=True).start()
    killer = threading.Timer(timeout, lambda: (proc.kill(), None))
    killer.start()
    try:
        for line in proc.stdout:
            if line.startswith("{"):
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ev["_t"] = round(time.time() - t0, 2)
                events.append(ev)
        proc.wait()
    finally:
        killer.cancel()
    timed_out = proc.returncode is not None and time.time() - t0 >= timeout - 1
    return {"exit": proc.returncode, "timed_out": timed_out, "seconds": round(time.time() - t0, 1),
            "events": events, "stderr": "".join(err)[-1500:]}


def rows(events: list[dict]) -> list[list]:
    """Same shape as the corpus snapshots: check, status, slide, shape id, subject."""
    return sorted([e["check_id"], e["status"], e.get("slide") or 0, e.get("shape_id") or 0, e.get("subject")]
                  for e in events if e.get("type") == "finding")


def stage_times(events: list[dict]) -> dict:
    """Seconds spent per progress stage (scan, fix, fit round n, safety, rescan, render)."""
    marks = []
    for e in events:
        if e.get("type") == "progress":
            name = f"fit{e['round']}" if e.get("stage") == "fit" else e.get("stage")
            if not marks or marks[-1][0] != name:
                marks.append((name, e["_t"]))
    end = events[-1]["_t"] if events else 0
    out = {}
    for (name, t), nxt in zip(marks, marks[1:] + [(None, end)]):
        out[name] = round(out.get(name, 0) + nxt[1] - t, 1)
    return out


def summarize(step: dict) -> dict:
    ev = step["events"]
    summary = next((e for e in ev if e.get("type") == "summary"), None)
    return {
        "exit": step["exit"], "timed_out": step["timed_out"], "seconds": step["seconds"],
        "stages": stage_times(ev),
        "summary": {k: v for k, v in (summary or {}).items() if k not in ("type", "input", "output", "_t")},
        "findings": rows(ev),
        "evidence": [{k: e.get(k) for k in ("check_id", "status", "slide", "shape_id", "subject", "message", "evidence")}
                     for e in ev if e.get("type") == "finding"],
        "changes": [[e.get("check_id"), e.get("slide"), e.get("shape_id"), e.get("prop"), e.get("before"), e.get("after")]
                    for e in ev if e.get("type") == "change"],
        "warnings": [e.get("message", "") for e in ev if e.get("type") in ("warn", "error")],
        "stderr": step["stderr"] if step["exit"] else "",
    }


def run_deck(deck: Path, suite: Path, run_dir: Path, layout: bool, images: bool, timeout: float) -> dict:
    rec = {"deck": str(deck.relative_to(suite)).replace("\\", "/"), "name": deck.name,
           "bytes": deck.stat().st_size, "sha256": sha256(deck)}
    key = rec["sha256"][:12]
    flags = ["--layout"] if layout else ["--no-layout"]
    with tempfile.TemporaryDirectory(prefix="st-suite-") as tmp:
        tmp = Path(tmp)
        rec["scan"] = summarize(run_cli(["scan", str(deck), "--json", *flags], timeout))
        review = run_dir / "images" / key if images else tmp / "review"
        repair_args = ["repair", str(deck), "--json", "--out", str(tmp / "once.pptx"), "--review-dir", str(review), *flags]
        if not layout:
            repair_args.append("--no-visual")
        rec["repair"] = summarize(run_cli(repair_args, timeout))
        if (tmp / "once.pptx").exists():
            again = run_cli(["repair", str(tmp / "once.pptx"), "--json", "--out", str(tmp / "twice.pptx"),
                             "--review-dir", str(tmp / "review2"), "--no-visual", *flags], timeout)
            rec["second_repair_changes"] = sum(1 for e in again["events"] if e.get("type") == "change")
            rec["second_repair_exit"] = again["exit"]
        media = run_cli(["media", str(deck), "--json"], min(timeout, 600))
        inv = next((e for e in media["events"] if e.get("type") == "media"), {})
        rec["media"] = {"inventory": inv.get("inventory", []), "downloads": inv.get("downloads", []),
                        "totals": inv.get("totals"), "exit": media["exit"]}
        if images and (review / "review.json").exists():
            for junk in ("prefit.pptx", "report.html"):
                (review / junk).unlink(missing_ok=True)       # keep the images + review.json only
    (run_dir / "decks").mkdir(parents=True, exist_ok=True)
    (run_dir / "decks" / f"{key}.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--suite", required=True, help="the shared 'SlideTistic Test Suite' folder")
    ap.add_argument("--layout", action="store_true", help="use PowerPoint (layout fixes + visual review), as the app does")
    ap.add_argument("--images", action="store_true", help="keep the before/after slide images (needs --layout)")
    ap.add_argument("--only", help="glob on the deck's path inside the suite, e.g. 'media/*'")
    ap.add_argument("--timeout", type=float, help="seconds per engine step (default 600, or 2400 with --layout)")
    ap.add_argument("--label", default="", help="extra word for the run folder name")
    args = ap.parse_args()

    suite = Path(args.suite)
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)
    from engine import __version__
    from engine.render import PowerPointRenderer
    commit = git("rev-parse", "--short=7", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    name = "-".join(x for x in (stamp, plat(), commit + ("+dirty" if dirty else ""),
                                "layout" if args.layout else "nolayout", args.label) if x)
    run_dir = suite / "_runs" / name
    run_dir.mkdir(parents=True)
    ok, why = PowerPointRenderer.available()
    run = {"run": name, "platform": plat(), "os": platform.platform(), "machine": platform.node(),
           "python": platform.python_version(), "engine": __version__, "commit": commit, "dirty": dirty,
           "layout": args.layout, "images": args.images,
           "renderer": {"name": PowerPointRenderer.name, "available": ok, "why": why},
           "powerpoint": powerpoint_version(),
           "poppler": tool_version("pdftotext", ["-v"]), "ffprobe": tool_version("ffprobe", ["-version"]),
           "started": dt.datetime.now().isoformat(timespec="seconds"), "decks": []}
    (run_dir / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")

    decks = find_decks(suite, args.only)
    timeout = args.timeout or (2400 if args.layout else 600)
    print(f"{len(decks)} decks → {run_dir}", flush=True)
    for i, deck in enumerate(decks, 1):
        t = time.time()
        try:
            rec = run_deck(deck, suite, run_dir, args.layout, args.images, timeout)
        except Exception as e:      # noqa: BLE001 — one bad deck must not stop the run
            rec = {"deck": str(deck.relative_to(suite)), "error": f"{type(e).__name__}: {e}"}
        rep = rec.get("repair", {})
        line = {"deck": rec["deck"], "sha12": rec.get("sha256", "")[:12], "seconds": round(time.time() - t, 1),
                "repair_exit": rep.get("exit"), "timed_out": rep.get("timed_out") or rec.get("scan", {}).get("timed_out"),
                "counts": {k: rep.get("summary", {}).get(k) for k in ("green_fixed", "yellow", "red", "tool_error")},
                "second_repair_changes": rec.get("second_repair_changes"), "warnings": rep.get("warnings", [])[:3],
                "error": rec.get("error")}
        run["decks"].append(line)
        (run_dir / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
        print(f"[{i}/{len(decks)}] {line['seconds']:>7}s exit={line['repair_exit']} timeout={bool(line['timed_out'])} "
              f"{line['counts']} 2nd={line['second_repair_changes']} {('ERR ' + line['error']) if line['error'] else ''}"
              f"{' WARN ' + '; '.join(line['warnings']) if line['warnings'] else ''} {rec['deck']}", flush=True)
    run["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    (run_dir / "run.json").write_text(json.dumps(run, indent=1), encoding="utf-8")
    print(f"done: {run_dir}", flush=True)


if __name__ == "__main__":
    main()
