"""Run every adversarial deck through the CLI the way the app does, without PowerPoint, and save what came out.

    venv/bin/python -m tests.fixtures.adversarial.run_all --out <folder>

For each deck: `scan --json --no-layout`, then `repair --json --no-layout --no-visual --no-report`, each in its
own process with a time limit. Writes <out>/<deck>.json (exit codes, seconds, events, stderr tail) and
<out>/summary.md (one line per deck). Decks that aren't committed are built into <out>/_built first.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tests.test_adversarial import prepared
from .decks import SPECS

REPO = Path(__file__).resolve().parents[3]


def run(*args, timeout=600):
    t = time.monotonic()
    try:
        p = subprocess.run([sys.executable, "-m", "engine.cli", *args], cwd=REPO, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = "timeout", e.stdout or "", e.stderr or ""
    events = []
    for line in (out or "").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return {"rc": rc, "seconds": round(time.monotonic() - t, 2), "events": events,
            "stderr": (err or "")[-3000:], "traceback": "Traceback" in (err or "") + (out or "")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", help="deck name prefix")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = ["| Deck | scan rc | s | repair rc | s | red | yellow | notes | fixed | errors | changes |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for spec in SPECS:
        if args.only and not spec.name.startswith(args.only):
            continue
        work = out / "_work" / spec.name
        shutil.rmtree(work, ignore_errors=True)
        path = prepared(spec, work)
        sets = [f"--set={k}={v}" for k, v in spec.overrides.items()]
        scan = run("scan", str(path), "--json", "--no-layout", *sets)
        rep = run("repair", str(path), "--json", "--no-layout", "--no-visual", "--no-report",
                  "--out", str(work / "mended.pptx"), *sets)
        (out / f"{spec.name}.json").write_text(json.dumps({"deck": spec.name, "scan": scan, "repair": rep},
                                                           ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        s = next((e for e in rep["events"] if e.get("type") == "summary"), {})
        lines.append(f"| {spec.name} | {scan['rc']} | {scan['seconds']} | {rep['rc']} | {rep['seconds']} | "
                     f"{s.get('red', '')} | {s.get('yellow', '')} | {s.get('notes', '')} | {s.get('green_fixed', '')} | "
                     f"{s.get('tool_error', '')} | {s.get('changes', '')} |")
        print(lines[-1], flush=True)
        if spec.rename == "big":
            shutil.rmtree(work, ignore_errors=True)        # don't keep a 2 GB file around
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
