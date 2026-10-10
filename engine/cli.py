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
        sp.add_argument("--no-layout", dest="layout", action="store_false", help="skip layout checks/fixes (quick)")
        sp.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="override a value from rules/thresholds.yaml for this run (e.g. safe_zone_pct=7)")
        sp.add_argument("--no-diagnostic", action="store_true", help="hide the rule behind each call in the report")
        sp.add_argument("--review-dir", help="write the app's review bundle (review.json + slide images) here")
        if name == "repair":
            sp.add_argument("--no-report", action="store_true", help="skip the HTML report")
            sp.add_argument("--no-visual", action="store_true", help="report without before/after images (faster)")
            sp.add_argument("--fix", help="comma-separated ids to fix (default: each check's default)")
            sp.add_argument("--out", help="output .pptx path (default: '<name> - mended.pptx' beside input)")

    us = sub.add_parser("undo-slide", help="put one slide of a repaired deck back to how it was before layout fixes")
    us.add_argument("file", help="the repaired deck (changed in place; it's SlideTistic's own output)")
    us.add_argument("--prefit", required=True, help="the pre-layout copy saved by repair (review bundle)")
    us.add_argument("--slide", required=True, type=int)
    us.add_argument("--review-dir", help="update this review bundle (re-renders the slide's 'after' image)")
    us.add_argument("--json", action="store_true")

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
    if args.cmd == "undo-slide":
        return _undo_slide(path, args)

    config = runner.RunConfig(
        checks=_ids(args.checks),
        fixes=_ids(getattr(args, "fix", None)),
        preset=args.preset,
        crew_fonts=_ids(args.crew_fonts) or set(),
        layout=bool(args.layout if args.layout is not None else
                    (args.cmd == "repair" and not getattr(args, "no_visual", False)
                     and (not getattr(args, "no_report", False) or args.review_dir))),
        prefit_path=Path(args.review_dir) / "prefit.pptx" if args.review_dir and args.cmd == "repair" else None,
        overrides=_overrides(args.set),
    )
    if args.review_dir:
        Path(args.review_dir).mkdir(parents=True, exist_ok=True)
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
    """One PowerPoint render feeds both the app's review bundle (image files) and the HTML report
    (the same images embedded)."""
    import base64
    from copy import copy
    from . import bundle, report, visual
    from .render import PowerPointRenderer, RenderError
    review_dir = Path(args.review_dir) if args.review_dir else None
    want_html = not getattr(args, "no_report", False) and (args.cmd == "repair" or args.report)
    if not want_html and not review_dir:
        return None
    visuals, note = None, ""
    if not getattr(args, "no_visual", False) and (result.output_path or args.report or review_dir):
        ok, why = PowerPointRenderer.available()
        if ok:
            emit({"type": "progress", "stage": "render"})
            renderer = PowerPointRenderer()
            try:
                visuals = visual.plan(result, result.input_path, result.output_path)
                visual.render(visuals, result.input_path, result.output_path, renderer, image_dir=review_dir)
            except (RenderError, OSError) as e:
                visuals, note = None, f"Visual review skipped: {e}"
            finally:
                renderer.cleanup()
        else:
            note = f"Visual review skipped: {why}."
    elif args.cmd == "repair":
        note = "Visual review turned off."
    if review_dir:
        path = bundle.write(result, checks, config, review_dir, visuals=visuals, note=note,
                            prefit=config.prefit_path)
        emit({"type": "review", "path": str(path)})
    if not want_html:
        return None
    html_visuals = visuals
    if visuals and review_dir:          # embed the bundle's image files into the stand-alone report
        html_visuals = []
        for v in visuals:
            c = copy(v)
            for attr in ("before_png", "after_png"):
                name = getattr(v, attr)
                if name:
                    setattr(c, attr, "data:image/jpeg;base64," + base64.b64encode((review_dir / name).read_bytes()).decode())
            html_visuals.append(c)
    out = Path(args.report) if args.report else (
        review_dir / "report.html" if review_dir else result.output_path.with_name(result.output_path.stem + " report.html"))
    source = next((f.message for f in result.findings if f.check_id == "X001"), None)
    path = report.build(result, checks, out, source=source, visuals=html_visuals, visual_note=note, config=config,
                        diagnostic=not args.no_diagnostic)
    emit({"type": "report", "path": str(path)})
    return path


def _undo_slide(path: Path, args) -> int:
    """Restore one slide from the pre-layout copy (keeps font/media/other fixes), then re-render it."""
    import json as _json
    from copy import deepcopy
    from .core import Deck
    from .core.content import is_hidden
    from .render import PowerPointRenderer, RenderError
    emit = (lambda e: print(_json.dumps(e, default=str), flush=True)) if args.json else (lambda e: None)
    mended, prefit = Deck(path), Deck(args.prefit)
    n = args.slide
    if not 1 <= n <= len(mended.slides) or len(prefit.slides) != len(mended.slides):
        _fail(args.json, f"Slide {n} can't be undone: the decks don't match.")
        return 2
    el, src = mended.slides[n - 1]._element, prefit.slides[n - 1]._element
    for child in list(el):
        el.remove(child)
    for child in deepcopy(src):
        el.append(child)
    mended.save(path)
    image = None
    review_dir = Path(args.review_dir) if args.review_dir else None
    if review_dir and PowerPointRenderer.available()[0] and not is_hidden(mended.slides[n - 1]):
        renderer = PowerPointRenderer()
        try:
            page = sum(1 for s in mended.slides[:n] if not is_hidden(s))
            image = f"slide-{n}-after.jpg"
            (review_dir / image).write_bytes(renderer.page_image(renderer.to_pdf(path, "undo"), page))
        except (RenderError, OSError) as e:
            emit({"type": "warn", "message": f"Slide {n} was undone, but its picture couldn't be refreshed: {e}"})
            image = None
        finally:
            renderer.cleanup()
    if review_dir and (review_dir / "review.json").exists():
        data = _json.loads((review_dir / "review.json").read_text(encoding="utf-8"))
        for v in data.get("visuals", []):
            if v["slide"] == n:
                v["after_boxes"], v["undone"] = [], True
                if image:
                    v["after_png"] = image
        data["changes"] = [c for c in data.get("changes", []) if not (c.get("check_id", "").startswith("L") and c.get("slide") == n)]
        data.setdefault("undone_slides", []).append(n)
        (review_dir / "review.json").write_text(_json.dumps(data, default=str), encoding="utf-8")
    emit({"type": "undone", "slide": n, "after_png": image})
    if not args.json:
        print(f"Slide {n} restored to how it was before layout fixes. Saved: {path}")
    return 0


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


def _overrides(pairs: list[str]) -> dict:
    """KEY=VALUE threshold overrides from the app's Settings (numbers stay numbers)."""
    out = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        try:
            out[key.strip()] = float(value) if "." in value else int(value)
        except ValueError:
            out[key.strip()] = value.strip()
    return out


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
