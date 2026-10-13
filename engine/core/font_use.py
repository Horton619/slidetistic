"""Which fonts visible text actually uses (David 2026-10-12: a deck can name fonts that no text on any slide
shows: left in a master, layout, theme or an empty run. PowerPoint still warns about them, so they look
like problems when they aren't).

For every run with text on a slide, resolve its Latin typeface the way PowerPoint inherits it:
run → paragraph level in the shape's own list style → the matching layout placeholder → the matching master
placeholder → the master's title/body/other text style (non-placeholders: presentation default text style,
then the master's other style) → the theme's major/minor font for '+mj-lt' / '+mn-lt'.
Latin fonts are resolved through inheritance; East Asian / complex-script / symbol fonts count only where a
shown run names them. Approximate by design: good enough to tell "drawn somewhere" from "named but never drawn".
"""
from __future__ import annotations

from collections import defaultdict

from pptx.oxml.ns import qn

TITLE_TYPES = {"title", "ctrTitle"}
BODY_TYPES = {"body", "subTitle", "obj", None}      # an idx-only placeholder is a body/content one


def _ph(shape_el):
    nv = next((c for c in shape_el if c.tag.endswith("}nvSpPr") or c.tag.endswith("}nvGraphicFramePr")), None)
    ph = nv.find(f"{qn('p:nvPr')}/{qn('p:ph')}") if nv is not None else None
    if ph is None:
        return None
    return ph.get("type"), ph.get("idx")


def _lvl_latin(lst_style, lvl: int) -> str | None:
    if lst_style is None:
        return None
    node = lst_style.find(qn(f"a:lvl{lvl + 1}pPr"))
    latin = node.find(f"{qn('a:defRPr')}/{qn('a:latin')}") if node is not None else None
    return latin.get("typeface") if latin is not None else None


def _shape_lst(shape_el):
    body = shape_el.find(qn("p:txBody"))
    return body.find(qn("a:lstStyle")) if body is not None else None


def _match_ph(container_el, kind, idx):
    """The placeholder in a layout/master tree with the same idx (or, failing that, the same type)."""
    by_type = None
    for sp in container_el.iter(qn("p:sp")):
        ph = _ph(sp)
        if ph is None:
            continue
        t, i = ph
        if idx is not None and i == idx:
            return sp
        if by_type is None and t == kind and kind is not None:
            by_type = sp
    return by_type


class _Context:
    def __init__(self, deck):
        prs = deck.prs
        self.default_text = prs.part._element.find(qn("p:defaultTextStyle"))
        self.theme = {}

    def theme_fonts(self, master_part):
        key = id(master_part)
        if key not in self.theme:
            major = minor = None
            for rel in master_part.rels.values():
                if rel.reltype.endswith("/theme"):
                    from lxml import etree
                    root = etree.fromstring(rel.target_part.blob)
                    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
                    mj = root.find(f".//{a}majorFont/{a}latin")
                    mn = root.find(f".//{a}minorFont/{a}latin")
                    major = mj.get("typeface") if mj is not None else None
                    minor = mn.get("typeface") if mn is not None else None
            self.theme[key] = (major, minor)
        return self.theme[key]


def _resolve(face: str | None, major: str | None, minor: str | None) -> str | None:
    if face in ("+mj-lt", "+mj-ea", "+mj-cs"):
        return major
    if face in ("+mn-lt", "+mn-ea", "+mn-cs"):
        return minor
    return face


def _inherited(ctx, slide, shape_el, lvl):
    """The typeface a run with no font of its own gets."""
    layout = slide.slide_layout
    master = layout.slide_master
    face = _lvl_latin(_shape_lst(shape_el), lvl)
    ph = _ph(shape_el)
    if face is None and ph is not None:
        kind, idx = ph
        for container in (layout._element, master._element):
            match = _match_ph(container, kind, idx)
            if match is not None:
                face = face or _lvl_latin(_shape_lst(match), lvl)
                if face:
                    break
        if face is None:
            styles = master._element.find(qn("p:txStyles"))
            name = "p:titleStyle" if kind in TITLE_TYPES else "p:bodyStyle" if kind in BODY_TYPES else "p:otherStyle"
            face = _lvl_latin(styles.find(qn(name)) if styles is not None else None, lvl)
    elif face is None:
        face = _lvl_latin(ctx.default_text, lvl)
        if face is None:
            styles = master._element.find(qn("p:txStyles"))
            face = _lvl_latin(styles.find(qn("p:otherStyle")) if styles is not None else None, lvl)
    major, minor = ctx.theme_fonts(master.part)
    return _resolve(face or "+mn-lt", major, minor)


def _runs(body):
    """(paragraph pPr, level, run) for every run or field with visible text."""
    for p in body.iter(qn("a:p")):
        ppr = p.find(qn("a:pPr"))
        lvl = int(ppr.get("lvl", "0")) if ppr is not None else 0
        for r in p:
            if r.tag in (qn("a:r"), qn("a:fld")):
                t = r.find(qn("a:t"))
                if t is not None and (t.text or "").strip():
                    yield ppr, lvl, r


def _own_face(ppr, r, major, minor):
    rpr = r.find(qn("a:rPr"))
    latin = rpr.find(qn("a:latin")) if rpr is not None else None
    if latin is None and ppr is not None:
        latin = ppr.find(f"{qn('a:defRPr')}/{qn('a:latin')}")
    return _resolve(latin.get("typeface"), major, minor) if latin is not None else None


def _text_bodies(root):
    return root.iter(qn("p:txBody"), qn("a:txBody"), "{http://schemas.microsoft.com/office/drawing/2008/diagram}txBody",
                     "{http://schemas.openxmlformats.org/drawingml/2006/chart}rich")


def _shows(el) -> bool:
    """showMasterSp: does this slide/layout show the shapes of the layout/master behind it?"""
    return el.get("showMasterSp", "1") not in ("0", "false")


def visible_fonts(deck) -> dict[str, dict]:
    """casefolded family → {"family", "slides": sorted list, "runs": count} for fonts that visible text uses.
    Covers slide text (with inheritance), SmartArt and chart text on the slide, and the fixed (non-placeholder)
    text of the layout and master behind it unless the slide hides background graphics."""
    from lxml import etree
    ctx = _Context(deck)
    out: dict[str, dict] = defaultdict(lambda: {"family": None, "slides": set(), "runs": 0})

    def add(face, n):
        if face:
            item = out[face.casefold()]
            item["family"] = item["family"] or face
            item["slides"].add(n)
            item["runs"] += 1

    for n, slide in enumerate(deck.slides, 1):
        layout = slide.slide_layout
        master = layout.slide_master
        major, minor = ctx.theme_fonts(master.part)
        for shape_el in slide._element.iter(qn("p:sp"), qn("p:graphicFrame")):
            for body in shape_el.iter(qn("p:txBody"), qn("a:txBody")):
                for ppr, lvl, r in _runs(body):
                    face = _own_face(ppr, r, major, minor)
                    if face is None:
                        face = _inherited(ctx, slide, shape_el, lvl) if shape_el.tag == qn("p:sp") else minor
                    add(face, n)
                    # East Asian / complex-script / symbol fonts set on shown text: PowerPoint draws some
                    # characters with them (01-02 MASTER: 等线 in the PDF). Counted as drawn, conservatively.
                    rpr = r.find(qn("a:rPr"))
                    for tag in ("a:ea", "a:cs", "a:sym"):
                        el = rpr.find(qn(tag)) if rpr is not None else None
                        if el is not None and el.get("typeface"):
                            add(_resolve(el.get("typeface"), major, minor) if not el.get("typeface").startswith("+") else None, n)
        # SmartArt drawings and charts are separate parts; their text has its own fonts (CLARB 00: Raleway).
        for rel in slide.part.rels.values():
            if rel.is_external or not (rel.reltype.endswith("/diagramDrawing") or rel.reltype.endswith("/chart")):
                continue
            root = etree.fromstring(rel.target_part.blob)
            for body in _text_bodies(root):
                for ppr, _lvl, r in _runs(body):
                    add(_own_face(ppr, r, major, minor) or minor, n)
        # Fixed text on the layout and master is drawn on this slide too (Session 16: Poppins on a layout).
        behind = []
        if _shows(slide._element.find(qn("p:cSld")).getparent()):
            behind.append(layout._element)
            if _shows(layout._element):
                behind.append(master._element)
        for container in behind:
            for shape_el in container.iter(qn("p:sp")):
                if _ph(shape_el) is not None:
                    continue
                for body in shape_el.iter(qn("p:txBody")):
                    for ppr, lvl, r in _runs(body):
                        add(_own_face(ppr, r, major, minor) or _lvl_latin(_shape_lst(shape_el), lvl) or minor, n)
    return {k: {**v, "slides": sorted(v["slides"])} for k, v in out.items()}
