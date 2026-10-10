"""slidetistic CLI. With --json, prints one JSON object per line (SlideFluid's NDJSON style)."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
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
        sp.add_argument("--report", help="write the HTML report here (repair: default '<output> report.html')")
        sp.add_argument("--layout", action="store_true", default=None,
                        help="judge text as PowerPoint draws it (needs PowerPoint; on by default for repair)")
        sp.add_argument("--no-diagnostic", action="store_true", help="hide the rule behind each call in the report")
        if name == "repair":
            sp.add_argument("--no-report", action="store_true", help="skip the HTML report")
            sp.add_argument("--no-visual", action="store_true", help="report without before/after images (faster)")
            sp.add_argument("--fix", help="comma-separated ids to fix (default: each check's default)")
            sp.add_argument("--out", help="output .pptx path (default: '<name> - mended.pptx' beside input)")

    md = sub.add_parser("media", help="media inventory + download list")
    md.add_argument("file")
    md.add_argument("--csv", help="write the inventory to this .csv (download list goes beside it)")
    md.add_argument("--xlsx", help="write both lists to this .xlsx")
    md.add_argument("--json", action="store_true")

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
    problem = unreadable_reason(path)
    if problem:
        _fail(args.json, problem)
        return 2

    if args.cmd == "media":
        return _media(path, checks, args)

    config = runner.RunConfig(
        checks=_ids(args.checks),
        fixes=_ids(getattr(args, "fix", None)),
        preset=args.preset,
        crew_fonts=_ids(args.crew_fonts) or set(),
        layout=bool(args.layout if args.layout is not None else
                    (args.cmd == "repair" and not getattr(args, "no_visual", False) and not getattr(args, "no_report", False))),
    )
    emit = (lambda e: print(json.dumps(e, default=str), flush=True)) if args.json else (lambda e: None)

    try:
        if args.cmd == "scan":
            result = runner.scan(path, checks, config, emit)
        else:
            result = runner.repair(path, checks, config, Path(args.out) if args.out else None, emit)
    except zipfile.BadZipFile as e:
        runner.cleanup()
        _fail(args.json, f"{path.name} is damaged ({e}). Ask for a fresh copy; PowerPoint may be able to repair it.")
        return 1
    except Exception as e:  # noqa: BLE001 — unreadable/corrupt/locked deck: report, don't traceback
        runner.cleanup()    # a failed run must not leave PowerPoint copies behind (2026-10-10)
        _fail(args.json, f"Couldn't open {path.name}: {e}")
        return 1

    try:
        report = _write_report(result, checks, config, args, emit)
    finally:
        runner.cleanup()
    if not args.json:
        _print_human(result)
        if report:
            print(f"Report: {report}")
    return 0


def _write_report(result, checks, config, args, emit) -> Path | None:
    from . import report, visual
    from .render import PowerPointRenderer, RenderError
    if args.cmd == "scan" and not args.report or getattr(args, "no_report", False):
        return None
    out = Path(args.report) if args.report else result.output_path.with_name(result.output_path.stem + " report.html")
    source = next((f.message for f in result.findings if f.check_id == "X001"), None)
    visuals, note = None, ""
    if not getattr(args, "no_visual", False) and (result.output_path or args.report):
        ok, why = PowerPointRenderer.available()
        if ok:
            emit({"type": "progress", "stage": "render"})
            renderer = PowerPointRenderer()
            try:
                visuals = visual.plan(result, result.input_path, result.output_path)
                visual.render(visuals, result.input_path, result.output_path, renderer)
            except (RenderError, OSError) as e:
                visuals, note = None, f"Visual review skipped: {e}"
            finally:
                renderer.cleanup()
        else:
            note = f"Visual review skipped: {why}."
    elif args.cmd == "repair":
        note = "Visual review turned off."
    path = report.build(result, checks, out, source=source, visuals=visuals, visual_note=note, config=config,
                        diagnostic=not args.no_diagnostic)
    emit({"type": "report", "path": str(path)})
    return path


def _media(path: Path, checks, args) -> int:
    from . import export
    media_checks = [c for c in checks if c.id in ("M002", "M004", "M005", "M006")]
    result = runner.scan(path, media_checks, runner.RunConfig(checks={c.id for c in media_checks}))
    inventory, downloads = export.inventory_rows(result.findings), export.download_rows(result.findings)
    if args.json:
        print(json.dumps({"type": "media", "inventory": inventory, "downloads": downloads,
                          "totals": export.totals(inventory)}, default=str))
    if args.csv:
        out = Path(args.csv)
        export.write_csv(out, export.INVENTORY_COLUMNS, inventory)
        export.write_csv(out.with_name(out.stem + " - download list.csv"), export.DOWNLOAD_COLUMNS, downloads)
    if args.xlsx:
        export.write_xlsx(Path(args.xlsx), inventory, downloads)
    if not (args.json or args.csv or args.xlsx):
        for r in inventory:
            print(f"Slide {r['slide']:>3}  {r['kind']:<5} {r['duration'] or '?':>7}  {r['starts']:<17} {r['volume']:>6}  {r['media']}")
        print(export.totals(inventory))
        for r in downloads:
            print(f"Slide {r['slide']:>3}  DOWNLOAD  {r['site']:<14} {r['url']}")
    return 0


def unreadable_reason(path: Path) -> str | None:
    """Plain-English reason a path can't be opened as a deck, or None. Checked before python-pptx sees it."""
    import zipfile
    if not path.exists():
        return f"File not found: {path}"
    if path.is_dir():
        pics = [p for p in path.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        kind = "a folder of slide images" if pics else "a folder"
        return f"{path.name} is {kind}, not a PowerPoint file."
    if not zipfile.is_zipfile(path):
        return f"{path.name} isn't a valid PowerPoint file (it may be damaged, an old .ppt renamed, or still downloading)."
    with zipfile.ZipFile(path) as z:
        if "[Content_Types].xml" not in z.namelist():
            return f"{path.name} isn't a valid PowerPoint file (it may be damaged)."
    return None


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
