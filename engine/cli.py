"""slidetistic CLI. With --json, prints one JSON object per line (SlideFluid's NDJSON style)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from .core import registry, runner
from .core.findings import Status

ICON = {Status.GREEN_FIXED: "✓", Status.YELLOW: "!", Status.RED: "✕", Status.TOOL_ERROR: "?"}


def _emitter(json_mode: bool):
    """One JSON line per event (--json). Renderer heartbeats and busy marks reach the same stream."""
    from .core import events
    events.set_sink((lambda e: print(json.dumps(e, default=str), flush=True)) if json_mode else None)
    return events.emit


def main(argv=None) -> int:
    from .core import events
    events.install_stop_handler()
    try:
        return _main(argv)
    except SystemExit:
        runner.cleanup()        # stopped by the app: don't leave work folders behind
        raise


def _main(argv=None) -> int:
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
        sp.add_argument("--powerpoint-visible", action="store_true",
                        help="Mac: don't hide PowerPoint while it renders (default: hidden when SlideTistic starts it)")
        sp.add_argument("--partial-export", choices=("off", "check", "on"), default="off",
                        help="fit rounds 2+: export only the slides the last round changed (slow decks; 'check' "
                             "also exports the whole deck and reports any difference)")
        sp.add_argument("--shape-cache", choices=("on", "off", "check"),
                        help="remember shape lists between edits (default on; 'check' verifies every reuse)")
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

    cl = sub.add_parser("cleanup", help="delete PowerPoint work files left by finished or killed jobs")
    cl.add_argument("--all", action="store_true", help="every leftover, not just ones over 6 hours old")
    cl.add_argument("--json", action="store_true")

    op = sub.add_parser("open-at-slide", help="Mac: open a deck in PowerPoint at a slide (waits for any export)")
    op.add_argument("file")
    op.add_argument("--slide", type=int, default=1)
    op.add_argument("--json", action="store_true")

    fn = sub.add_parser("fonts", help="free fonts (F009): catalog, get, installed, uninstall")
    fsub = fn.add_subparsers(dest="fonts_cmd", required=True)
    fc = fsub.add_parser("catalog", help="update the free-font list if it's a week old (--refresh: now)")
    fc.add_argument("--refresh", action="store_true")
    fc.add_argument("--json", action="store_true")
    fg = fsub.add_parser("get", help="download (and with --install, install) a deck's free fonts")
    fg.add_argument("file")
    fg.add_argument("--family", action="append", help="only these families (default: every F009 finding)")
    fg.add_argument("--install", action="store_true")
    fg.add_argument("--json", action="store_true")
    fl = fsub.add_parser("collect", help="the deck's fonts in a folder next to it (links to installed ones)")
    fl.add_argument("file")
    fl.add_argument("--out", help="folder (default: '<deck> - fonts' next to the deck)")
    fl.add_argument("--json", action="store_true")
    fa = fsub.add_parser("adobe", help="which of these families Adobe Fonts has (Creative Cloud activation)")
    fa.add_argument("--family", action="append", required=True)
    fa.add_argument("--json", action="store_true")
    fh = fsub.add_parser("here", help="is each family on this computer now (installed, or via Creative Cloud)")
    fh.add_argument("--family", action="append", required=True)
    fh.add_argument("--link", action="append", default=[], help="the Adobe Fonts page of each --family, same order")
    fh.add_argument("--json", action="store_true")
    fi = fsub.add_parser("installed", help="fonts SlideTistic installed")
    fi.add_argument("--json", action="store_true")
    fu = fsub.add_parser("uninstall", help="remove fonts SlideTistic installed")
    fu.add_argument("family", nargs="?")
    fu.add_argument("--all", action="store_true")
    fu.add_argument("--json", action="store_true")
    tn = sub.add_parser("tune", help="report on David's 👍/👎 votes and propose layout-fix rules")
    tn.add_argument("--votes", help="feedback folder (default: the Dropbox suite's _feedback)")
    tn.add_argument("--apply", metavar="P#", help="add a proposal from the last report to rules/tuning.yaml")
    tn.add_argument("--out", help="write the report (Markdown) here")
    tn.add_argument("--json", action="store_true")
    md = sub.add_parser("media", help="media inventory + download list")
    md.add_argument("file")
    md.add_argument("--csv", help="write the inventory to this .csv (download list goes beside it)")
    md.add_argument("--xlsx", help="write both lists to this .xlsx")
    md.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    if getattr(args, "powerpoint_visible", False):
        from . import render as render_module
        render_module.PPT_HIDDEN = False
    if getattr(args, "shape_cache", None):
        from .core import deck as deck_module
        deck_module.SHAPE_CACHE = args.shape_cache
    checks = registry.discover()

    if args.cmd == "list-checks":
        meta = [c.metadata() for c in checks]
        if args.json:
            print(json.dumps(meta))
        else:
            for m in meta:
                print(f"{m['id']}  {m['title']}  [{m['group']}]  fix={'on' if m['default_fix'] else 'off'}")
        return 0

    if args.cmd == "fonts":
        return _fonts(args, checks)
    if args.cmd == "tune":
        from . import tune
        return tune.main(args)
    if args.cmd == "open-at-slide":
        from .render import open_at_slide
        problem = open_at_slide(Path(args.file), args.slide)
        print(json.dumps({"type": "opened", "ok": not problem, "error": problem}) if args.json else (problem or "Opened"))
        return 1 if problem else 0
    if args.cmd == "cleanup":
        from .keynote import purge_cache
        from .render import purge_leftovers
        freed = purge_leftovers(everything=args.all) + purge_cache(everything=args.all)
        print(json.dumps({"type": "cleanup", "freed_bytes": freed}) if args.json else f"Freed {freed / 1e6:.1f} MB")
        return 0

    path = Path(args.file)
    emit = _emitter(args.json)
    converted_from = None
    if path.suffix.lower() == ".key" and args.cmd in ("scan", "repair", "media"):
        # Keynote: Keynote itself exports a .pptx (Mac only), then everything below runs on that.
        from . import keynote
        emit({"type": "progress", "stage": "convert"})
        try:
            converted_from, path = path, keynote.convert(path)
        except keynote.KeynoteError as e:
            _fail(args.json, str(e))
            return 2
        if args.cmd == "repair" and not getattr(args, "out", None):
            args.out = str(converted_from.with_name(converted_from.stem + " - mended.pptx"))
        emit({"type": "converted", "from": str(converted_from), "app": (keynote.keynote_app() or ("", ""))[1]})
    if path.suffix.lower() != ".pptx":
        _fail(args.json, f"Only .pptx files can be checked (got {path.suffix or 'no extension'}).")
        return 2
    problem = unreadable_reason(path)
    if problem:
        _fail(args.json, problem)
        return 2

    args.converted_from = str(converted_from) if converted_from else None
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
        partial_export=args.partial_export,
    )
    if args.review_dir:
        Path(args.review_dir).mkdir(parents=True, exist_ok=True)
    emit = _emitter(args.json)

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
    from .render import STATS, MacPowerPointRenderer
    emit({"type": "timing", **{k: round(v, 2) for k, v in STATS.items()}})
    if MacPowerPointRenderer.force_quit_note:
        emit({"type": "warn", "message": MacPowerPointRenderer.force_quit_note})
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
            if review_dir:      # findings first: the app shows them while PowerPoint draws the slides
                path = bundle.write(result, checks, config, review_dir, prefit=config.prefit_path, pending=True,
                                    converted_from=getattr(args, "converted_from", None))
                emit({"type": "review", "path": str(path), "partial": True})
            emit({"type": "progress", "stage": "render"})
            # The layout pass's renderer still holds this job's PDFs (runner.cleanup() runs after the
            # report): reusing it skips re-exporting decks it already drew.
            shared = runner._RENDERER
            renderer = shared or PowerPointRenderer()
            try:
                visuals = visual.plan(result, result.input_path, result.output_path)
                visual.render(visuals, result.input_path, result.output_path, renderer, image_dir=review_dir)
            except (RenderError, OSError, subprocess.SubprocessError) as e:
                visuals, note = None, f"Visual review skipped: {e}"
            finally:
                if renderer is not shared:
                    renderer.cleanup()
        else:
            note = f"Visual review skipped: {why}."
    elif args.cmd == "repair":
        note = "Visual review turned off."
    if review_dir:
        path = bundle.write(result, checks, config, review_dir, visuals=visuals, note=note,
                            prefit=config.prefit_path, converted_from=getattr(args, "converted_from", None))
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
    emit = _emitter(args.json)
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
        except (RenderError, OSError, subprocess.SubprocessError) as e:
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
        if _encrypted(path):
            return (f"{path.name} is password-protected. Open it in PowerPoint with the password, remove it "
                    "(File ▸ Passwords, or Info ▸ Protect Presentation), save, and check that copy.")
        return f"{path.name} isn't a valid PowerPoint file (it may be damaged, an old .ppt renamed, or still downloading)."
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if "[Content_Types].xml" not in {i.filename for i in infos}:
            return f"{path.name} isn't a valid PowerPoint file (it may be damaged)."
        # A "zip bomb" (tiny file, enormous inside) would fill memory: python-pptx reads every XML part.
        # Real decks' XML parts are a few MB; media is stored, not expanded, so it's counted separately.
        if any(i.filename.endswith((".xml", ".rels")) and i.file_size > XML_PART_MAX for i in infos) \
                or sum(i.file_size for i in infos) > DECK_UNPACKED_MAX:
            return f"{path.name} unpacks to an implausible size; it may be damaged or crafted. Not opened."
        if _slide_list_broken(z):
            return (f"{path.name} is damaged: its slide list names a slide that isn't in the file. Open it in "
                    "PowerPoint (let it repair the file if it asks), save a copy, and check that.")
    return None


def _slide_list_broken(z) -> bool:
    """A slide in presentation.xml's list with no relationship, or a relationship to a missing part. Every check
    would fail on its own (adversarial round 1: 32 tool_errors); one plain message instead."""
    import posixpath
    from lxml import etree
    names = set(z.namelist())
    try:
        pres = etree.fromstring(z.read("ppt/presentation.xml"))
        rels = etree.fromstring(z.read("ppt/_rels/presentation.xml.rels"))
    except (KeyError, etree.XMLSyntaxError):
        return False                # not this problem; python-pptx will say what's wrong
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    targets = {r.get("Id"): r.get("Target", "") for r in rels}
    for sld in pres.iter("{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"):
        target = targets.get(sld.get(R))
        if target is None:
            return True
        part = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join("ppt", target))
        if part not in names:
            return True
    return False


def _encrypted(path: Path) -> bool:
    """A password-protected .pptx is an OLE compound file (like an old .ppt) holding 'EncryptionInfo' and
    'EncryptedPackage' streams; their names sit in the file's directory, near the start in practice."""
    import struct
    try:
        with open(path, "rb") as f:
            head = f.read(512)
            if head[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
                return False
            data = head + f.read(1024 * 1024)
            # The directory's first sector, from the header (sector size 2**shift); big files put it anywhere.
            shift, first_dir = struct.unpack_from("<H", head, 0x1E)[0], struct.unpack_from("<I", head, 0x30)[0]
            f.seek((first_dir + 1) << shift)
            data += f.read(64 << shift)
    except (OSError, struct.error):
        return False
    return "EncryptedPackage".encode("utf-16-le") in data or "EncryptionInfo".encode("utf-16-le") in data


XML_PART_MAX = 256 * 1024 * 1024
DECK_UNPACKED_MAX = 32 * 1024 ** 3


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


def _fonts(args, checks) -> int:
    """JSON-lines events with --json (the app's Get fonts button), plain lines otherwise."""
    from .core import fonts_catalog, fonts_install
    out = (lambda ev: print(json.dumps(ev), flush=True)) if args.json else (lambda ev: print(ev.get("message", ev)))
    if args.fonts_cmd == "catalog":
        try:
            st = fonts_catalog.refresh(force=args.refresh)      # without --refresh: only when a week old
        except Exception as e:  # noqa: BLE001 — network boundary: report, don't crash
            out({"type": "error", "message": f"Couldn't download the font list: {e}"})
            return 1
        out({"type": "catalog", **st, "message": f"{st['families']} free fonts, list from {st['fetched'] or 'never'}"})
        return 0
    if args.fonts_cmd == "collect":
        try:
            fonts_catalog.refresh()
        except Exception as e:  # noqa: BLE001 — offline: the saved list still works
            out({"type": "warn", "message": f"Font list not refreshed ({e}); using the saved one"})
        res = fonts_install.collect(args.file, args.out, emit=out)
        for f in res["fonts"]:
            out({"type": "font", **f, "message": f"{f['name']}: {f['how']}"})
        out({"type": "done", "folder": res["folder"], "message": f"Fonts collected in {res['folder']}"})
        return 0
    if args.fonts_cmd == "adobe":
        from .core import adobe_fonts
        for fam, info in adobe_fonts.lookup(args.family).items():
            out({"type": "adobe", "family": fam, "info": info, "search": adobe_fonts.search_link(fam),
                 "message": f"{fam}: {info['link'] if info else 'not on Adobe Fonts'}"})
        return 0
    if args.fonts_cmd == "here":
        from .core import adobe_fonts
        have = fonts_install.installed()
        links = args.link + [None] * len(args.family)
        for fam, link in zip(args.family, links):
            keys = {fam.casefold(), adobe_fonts.base_family(fam).casefold()}
            where = ("creative_cloud" if keys & have["creative_cloud"] else "installed" if keys & have["families"] else None)
            state = adobe_fonts.added_state(fam, link)
            if where is None and state == "OS":
                where = "creative_cloud"
            elif where is None and state == "CC":
                where = "adobe_apps_only"       # added, but only Adobe's apps can use it: PowerPoint can't
            out({"type": "here", "family": fam, "here": where, "message": f"{fam}: {where or 'not on this computer'}"})
        return 0
    if args.fonts_cmd == "installed":
        for e in fonts_install._log():
            out({"type": "installed", **e, "message": f"{e['family']}: {e['file']}"})
        return 0
    if args.fonts_cmd == "uninstall":
        if not args.family and not args.all:
            out({"type": "error", "message": "Name a family, or --all"})
            return 2
        for f in fonts_install.uninstall(None if args.all else args.family):
            out({"type": "removed", "file": f, "message": f"Removed {f}"})
        return 0
    # get
    from .core import Deck
    from .core.runner import RunConfig, make_context
    try:
        fonts_catalog.refresh()
    except Exception as e:  # noqa: BLE001 — offline: the cached list still works
        out({"type": "warn", "message": f"Font list not refreshed ({e}); using the saved one"})
    f009 = next(c for c in checks if c.id == "F009")
    wanted = {f.casefold() for f in args.family or []}
    found = [f for f in f009().detect(Deck(args.file), make_context(RunConfig())) if f.subject != "catalog"
             and (not wanted or f.subject.casefold() in wanted)]
    if not found:
        out({"type": "done", "families": 0, "message": "No free fonts to get for this deck"})
        return 0
    code = 0
    for f in found:
        variants = [tuple(v) for v in f.evidence["variants"]]
        out({"type": "progress", "family": f.subject, "message": f"Downloading {f.subject}…"})
        try:
            files = fonts_install.download(f.subject, variants)
            license_ = f.evidence.get("license")
            if not license_ and f.evidence.get("source") == "fontsource":
                license_ = fonts_catalog.details(f.evidence["font_id"]).get("license")
            license_ = license_ or "open licence (Google Fonts)"
        except Exception as e:  # noqa: BLE001 — network boundary
            out({"type": "font", "family": f.subject, "ok": False, "message": f"{f.subject}: download failed ({e})"})
            code = 1
            continue
        results = fonts_install.install(f.subject, files, deck=str(args.file)) if args.install else \
            [{**fonts_install._strip(x), "installed": False} for x in files]
        ok = all(r.get("installed") or r.get("problem") == "already installed" for r in results) if args.install \
            else all(x["problem"] is None for x in files)
        out({"type": "font", "family": f.subject, "license": license_, "ok": ok, "files": results,
             "message": f"{f.subject} ({license_}): " + ", ".join(
                 f"{x['weight']}{' italic' if x['style'] == 'italic' else ''} "
                 f"{'installed' if x.get('installed') else x.get('problem') or 'ready'}" for x in results)})
        code = code or (0 if ok else 1)
    out({"type": "done", "families": len(found), "installed": args.install,
         "message": "Restart PowerPoint to use the new fonts." if args.install else "Downloaded and checked (not installed)."})
    return code


if __name__ == "__main__":
    sys.exit(main())
