"""Adversarial decks (docs/ADVERSARIAL_DECKS.md, tests/fixtures/adversarial/): every deck is scanned and repaired
without PowerPoint and checked against what SlideTistic SHOULD report. Known misses and false alarms are
xfail(strict) with the reason: that list is the to-do list (docs/ADVERSARIAL_RESULTS.md). When one starts
passing, pytest says XPASS(strict) and the Spec's xfail should be removed.

Layout decks (Spec.layout) are only checked for "no crash, nothing broken" here; David runs them on the Mac.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest
from pptx.oxml.ns import qn

from engine.core import Deck, registry
from engine.core.findings import Status
from engine.core.media import ffprobe_path
from engine.core.runner import RunConfig, repair, scan
from tests.fixtures.adversarial import build as adv_build
from tests.fixtures.adversarial.decks import SPECS, E, Spec

REPO = Path(__file__).resolve().parent.parent
CHECKS = registry.discover()
COMMITTED = adv_build.DECKS
PROBLEM = (Status.RED, Status.YELLOW)

DATA = [s for s in SPECS if s.kind != "robust" or s.outcome == "ok"]
ROBUST = [s for s in SPECS if s.kind == "robust"]


def _id(spec):
    return spec.name


def _xfail(reason):
    return [pytest.mark.xfail(reason=reason, strict=True)] if reason else []


def params(specs, attr="xfail", cli=False):
    """A robust deck's `xfail` is about the CLI (test_engine_survives); in-process tests use repair_xfail."""
    def reason(s):
        return None if attr == "xfail" and s.kind == "robust" and not cli else getattr(s, attr)
    return [pytest.param(s, id=_id(s), marks=_xfail(reason(s)) + ([pytest.mark.slow] if s.slow else []))
            for s in specs]


# --- getting a deck ready -----------------------------------------------------------------------

def prepared(spec: Spec, folder: Path) -> Path:
    """The deck in its own folder, under the file name and path the Spec asks for."""
    folder.mkdir(parents=True, exist_ok=True)
    if spec.commit:
        src = COMMITTED / spec.file
        assert src.exists(), f"{spec.file} is missing: run `venv/bin/python -m tests.fixtures.adversarial.build`"
    else:
        src = adv_build.build(spec, folder / "_built")
    target = folder / spec.file
    if spec.rename in ("deep", "big") and sys.platform == "win32":
        pytest.skip("Windows: a >260-character path can't be created here, and a seek doesn't make a sparse file")
    if spec.rename == "deep":
        deep = folder
        while len(str(deep / spec.file)) <= 270:
            deep = deep / "Conference Materials Final Versions"
        deep.mkdir(parents=True, exist_ok=True)
        target = deep / spec.file
    elif spec.rename == "big":
        target = folder / spec.file
        with src.open("rb") as f_in, target.open("wb") as f_out:
            f_out.seek(2 * 1024 ** 3)            # a sparse 2 GB hole, then a valid zip
            f_out.write(f_in.read())
        return target
    elif spec.rename:
        target = folder / spec.rename
    shutil.copyfile(src, target)
    if spec.sidecar:
        shutil.copyfile(REPO / "engine" / "assets" / "media_stubs" / "stub.mp4", target.parent / spec.sidecar)
    return target


def needs(spec):
    if "ffprobe" in spec.needs and not ffprobe_path():
        pytest.skip("needs ffprobe")
    if "catalog" in spec.needs:
        from engine.core import fonts_catalog
        if not fonts_catalog.available():
            pytest.skip("needs the cached free-font catalog (tests run with an empty font cache)")


def config(spec, **kw):
    return RunConfig(layout=False, overrides=dict(spec.overrides), **kw)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > 256 * 1024 ** 2:      # the sparse 2 GB deck: its zip is at the end
            f.seek(size - (64 << 20))
            return f"{size}:{path.stat().st_mtime_ns}:" + hashlib.sha256(f.read()).hexdigest()
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run_or_skip(spec, fn, *a, **kw):
    """Robustness decks may be refused by python-pptx in-process; test_engine_survives judges those via the CLI."""
    try:
        return fn(*a, **kw)
    except Exception as e:  # noqa: BLE001
        if spec.kind == "robust":
            pytest.skip(f"refused in-process ({type(e).__name__}); see test_engine_survives")
        raise


# --- matching ----------------------------------------------------------------------------------

def matches(f, e: E) -> bool:
    if f.check_id != e.check:
        return False
    if e.slide is not None and f.slide != e.slide:
        return False
    if e.subject is not None and e.subject.casefold() not in (f.subject or "").casefold():
        return False
    st = e.status
    if st == "info":
        return f.informational
    if f.informational:
        return False
    if st == "note":
        return f.is_note
    if st == "problem":
        return f.status == Status.RED or (f.status == Status.YELLOW and not f.is_note)
    if st == "yellow":
        return f.status == Status.YELLOW and not f.is_note
    return f.status.value == st


def absent_violations(findings, absent) -> list:
    out = []
    for a in absent:
        if isinstance(a, E):
            hits = [f for f in findings if matches(f, a)]
        elif isinstance(a, (tuple, list)):
            hits = [f for f in findings if matches(f, E(a[0], a[1]))]
        else:
            hits = [f for f in findings if f.check_id == a and not f.informational and f.status in PROBLEM
                    and not f.is_note]
        out += [f"{f.check_id} {f.status.value} s{f.slide}: {f.message}" for f in hits]
    return out


def _check_of(e) -> str:
    return e.check if hasattr(e, "check") else (e[0] if isinstance(e, (tuple, list)) else str(e))


def describe(findings) -> str:
    return "\n".join(f"  {f.check_id} {f.status.value}{' (note)' if f.is_note else ''}"
                     f"{' (info)' if f.informational else ''} s{f.slide} [{f.subject}] {f.message[:110]}"
                     for f in findings)


# --- scans --------------------------------------------------------------------------------------

@pytest.mark.parametrize("spec", params(DATA))
def test_scan_reports_what_it_should(spec, tmp_path):
    needs(spec)
    path = prepared(spec, tmp_path)
    before = digest(path)
    result = run_or_skip(spec, scan, path, CHECKS, config(spec))
    assert digest(path) == before, "a scan changed the input file"
    errors = [f for f in result.findings if f.status == Status.TOOL_ERROR]
    if spec.kind != "robust":
        assert not errors, "a check crashed:\n" + describe(errors)
    # A layout deck's L-check expectations need PowerPoint: they're checked on David's Mac (suite --layout).
    expect = [e for e in spec.expect if not (spec.layout and _check_of(e).startswith("L"))]
    missing = [str(e) for e in expect if not any(matches(f, e) for f in result.findings)]
    wrong = absent_violations(result.findings, spec.absent)
    assert not missing and not wrong, (f"missing: {missing}\nshould not be there: {wrong}\nfound:\n"
                                       + describe(result.findings))
    if spec.layout or spec.kind == "layout":
        layout = [f for f in result.findings if f.check_id.startswith("L") and f.status in PROBLEM]
        assert not layout, "layout checks must stay silent without PowerPoint:\n" + describe(layout)


# --- repairs ------------------------------------------------------------------------------------

def _pictures(path: Path) -> list:
    """(slide, name, position) of every picture: off-slide rules never move pictures (CLAUDE.md rule 5)."""
    out = []
    try:
        slides = Deck(path).slides
    except Exception as e:  # noqa: BLE001 — a damaged robustness deck: nothing to compare
        return [repr(e)]
    for n, slide in enumerate(slides, 1):
        for pic in slide._element.iter(qn("p:pic")):
            off = pic.find(".//" + qn("a:off"))
            ext = pic.find(".//" + qn("a:ext"))
            name = pic.find(".//" + qn("p:cNvPr")).get("name")
            out.append((n, name, dict(off.attrib) if off is not None else None, dict(ext.attrib) if ext is not None else None))
    return out


def _typefaces(path: Path) -> set[str]:
    from engine.core import fonts
    return {r.typeface for r in fonts.font_refs(Deck(path))}


def _repair(spec, tmp_path):
    needs(spec)
    path = prepared(spec, tmp_path / "in")
    before = digest(path)
    out = tmp_path / "out" / "mended.pptx"
    out.parent.mkdir()
    result = run_or_skip(spec, repair, path, CHECKS, config(spec), out_path=out)
    assert digest(path) == before, "repair changed the input file"
    return path, result


@pytest.mark.parametrize("spec", params(DATA, "safe_xfail"))
def test_repair_is_safe(spec, tmp_path):
    """Every deck: no X000 (lost words/shapes/media), no crashed fix, pictures never moved, a second repair
    changes nothing."""
    path, result = _repair(spec, tmp_path)
    broken = [f for f in result.findings if f.check_id == "X000" or
              (f.status == Status.TOOL_ERROR and spec.kind != "robust")]
    assert not broken, "repair broke something:\n" + describe(broken)
    assert _pictures(path) == _pictures(result.output_path), "a picture was moved or resized"
    again = repair(result.output_path, CHECKS, config(spec), out_path=tmp_path / "out" / "mended twice.pptx")
    assert not again.changes, "a second repair still changed: " + "; ".join(
        f"{c.check_id} s{c.slide} {c.prop}: {c.before} → {c.after}" for c in again.changes[:8])


@pytest.mark.parametrize("spec", params([s for s in DATA if s.fixed or s.kept_fonts or s.gone_fonts], "repair_xfail"))
def test_repair_fixes_what_it_should(spec, tmp_path):
    _, result = _repair(spec, tmp_path)
    for cid in spec.fixed:
        mine = [f for f in result.findings if f.check_id == cid and not f.informational and not f.is_note]
        assert mine, f"{cid} found nothing to fix:\n" + describe(result.findings)
        left = [f for f in mine if f.status != Status.GREEN_FIXED]
        assert not left, f"{cid} not fixed:\n" + describe(left)
    faces = _typefaces(result.output_path)
    assert not [f for f in spec.kept_fonts if f not in faces], f"renamed a real font: {spec.kept_fonts} not in {faces}"
    assert not [f for f in spec.gone_fonts if f in faces], f"still there: {[f for f in spec.gone_fonts if f in faces]}"


# --- robustness through the CLI, as the app runs it ----------------------------------------------

def _cli(*args, timeout=180):
    t = time.monotonic()
    proc = subprocess.run([sys.executable, "-m", "engine.cli", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    return proc, time.monotonic() - t


@pytest.mark.parametrize("spec", params(ROBUST, cli=True))
def test_engine_survives(spec, tmp_path):
    """Plain error or a clean run; never a traceback, a hang or a changed input."""
    path = prepared(spec, tmp_path / "in")
    before = digest(path)
    for cmd in (["scan", str(path), "--json", "--no-layout"],
                ["repair", str(path), "--json", "--no-layout", "--no-visual", "--no-report",
                 "--out", str(tmp_path / "mended.pptx")]):
        proc, secs = _cli(*cmd)
        assert "Traceback" not in proc.stderr and "Traceback" not in proc.stdout, proc.stderr[-2000:]
        events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
        errors = [e["message"] for e in events if e.get("type") == "error"]
        if spec.outcome == "error":
            assert proc.returncode != 0 and errors, f"expected a plain refusal, got rc={proc.returncode}"
        else:
            assert proc.returncode == 0, f"rc={proc.returncode}: {errors or proc.stderr[-500:]}"
            crashed = [e for e in events if e.get("type") == "finding" and e.get("status") == "tool_error"]
            assert len(crashed) <= 1, f"{len(crashed)} checks crashed: {crashed[0]['message']}"
        if spec.name == "R-zip-bomb":
            assert secs < 10, f"took {secs:.1f} s to refuse"
        if spec.name == "R-encrypted":
            assert any("password" in m.lower() for m in errors), errors
    assert digest(path) == before, "the input file changed"


def test_render_copy_neutralises_planted_links(tmp_path):
    """R-render-safety: the copy PowerPoint opens must not reach a server or run anything (deck.render_safe)."""
    from engine.core.deck import LINK_REMOVED, write_render_copy
    spec = next(s for s in SPECS if s.name == "R-render-safety")
    path = prepared(spec, tmp_path)
    copy = tmp_path / "render.pptx"
    write_render_copy(path, copy)
    with zipfile.ZipFile(copy) as z:
        for name in z.namelist():
            data = z.read(name)
            if name.endswith(".rels"):
                for marker in (b"203.0.113.5", b"/activeX", b"vbaProject"):
                    assert marker not in data, f"{name} still has {marker!r}"
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                assert b"<p:controls" not in data
        assert any(LINK_REMOVED.encode() in z.read(n) for n in z.namelist() if n.endswith(".rels"))


def test_every_committed_deck_is_in_the_catalogue():
    known = {s.file for s in SPECS if s.commit}
    on_disk = {p.name for p in COMMITTED.glob("*.pptx")}
    assert on_disk == known, f"stale: {sorted(on_disk - known)}; not built: {sorted(known - on_disk)}"


def test_manifest_is_current():
    assert (adv_build.HERE / "MANIFEST.md").read_text(encoding="utf-8") == adv_build.manifest(), \
        "MANIFEST.md is stale: run `venv/bin/python -m tests.fixtures.adversarial.build`"


def test_shapes_sharing_an_id_are_never_fixed(tmp_path):
    """R-duplicate-shape-ids (2026-10-14): two boxes with one id. Neither moves, both stay red and say why."""
    spec = next(s for s in SPECS if s.name == "R-duplicate-shape-ids")
    _, result = _repair(spec, tmp_path)
    reds = [f for f in result.findings if f.check_id == "G001" and f.status == Status.RED]
    assert len(reds) == 2 and all("share this shape's id" in f.message or "share" in str(f.evidence) for f in reds), \
        describe(result.findings)
    assert not [c for c in result.changes if c.check_id == "G001"]
