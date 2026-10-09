"""slidetistic CLI. With --json, prints one JSON object per line (SlideFluid's NDJSON style)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import registry, runner
from .core.findings import Status

ICON = {Status.GREEN_FIXED: "✓", Status.YELLOW: "!", Status.RED: "✕", Status.TOOL_ERROR: "?"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="slidetistic")
    sub = p.add_subparsers(dest="cmd", required=True)

    lc = sub.add_parser("list-checks")
    lc.add_argument("--json", action="store_true")

    for name in ("scan", "repair"):
        sp = sub.add_parser(name)
        sp.add_argument("file")
        sp.add_argument("--preset", default="any")
        sp.add_argument("--checks", help="comma-separated ids to run (default: each check's default)")
        sp.add_argument("--crew-fonts", help="comma-separated fonts installed on the show machines")
        sp.add_argument("--json", action="store_true")
        if name == "repair":
            sp.add_argument("--fix", help="comma-separated ids to fix (default: each check's default)")
            sp.add_argument("--out", help="output .pptx path (default: '<name> - mended.pptx' beside input)")

    args = p.parse_args(argv)
    checks = registry.discover()

    if args.cmd == "list-checks":
        meta = [c.metadata() for c in checks]
        if args.json:
            print(json.dumps(meta))
        else:
            for m in meta:
                print(f"{m['id']}  {m['title']}  [{m['group']}]  fix={'on' if m['default_fix'] else 'off'}")
        return 0

    path = Path(args.file)
    if path.suffix.lower() != ".pptx":
        _fail(args.json, f"Only .pptx files can be checked (got {path.suffix or 'no extension'}).")
        return 2
    if not path.exists():
        _fail(args.json, f"File not found: {path}")
        return 2

    config = runner.RunConfig(
        checks=_ids(args.checks),
        fixes=_ids(getattr(args, "fix", None)),
        preset=args.preset,
        crew_fonts=_ids(args.crew_fonts) or set(),
    )
    emit = (lambda e: print(json.dumps(e, default=str), flush=True)) if args.json else (lambda e: None)

    try:
        if args.cmd == "scan":
            result = runner.scan(path, checks, config, emit)
        else:
            result = runner.repair(path, checks, config, Path(args.out) if args.out else None, emit)
    except Exception as e:  # noqa: BLE001 — unreadable/corrupt/locked deck: report, don't traceback
        _fail(args.json, f"Couldn't open {path.name}: {e}")
        return 1

    if not args.json:
        _print_human(result)
    return 0


def _ids(s: str | None) -> set[str] | None:
    return None if s is None else {x.strip() for x in s.split(",") if x.strip()}


def _fail(as_json: bool, message: str):
    if as_json:
        print(json.dumps({"type": "error", "message": message}), flush=True)
    else:
        print(message, file=sys.stderr)


def _print_human(result: runner.Result):
    for f in result.findings:
        where = (f"Slide {f.slide}" + (f" · {f.shape_name}" if f.shape_name else "")) if f.slide else "Deck"
        print(f"{ICON.get(f.status, '·')} {f.check_id}  {where}: {f.message}")
    s = result.summary()
    print(f"\n{s['green_fixed']} fixed · {s['yellow']} to look at · {s['red']} still broken"
          + (f" · {s['tool_error']} couldn't run" if s["tool_error"] else ""))
    if result.output_path:
        print(f"Saved: {result.output_path}")


if __name__ == "__main__":
    sys.exit(main())
