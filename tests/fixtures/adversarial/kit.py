"""Raw-XML helpers for the adversarial decks (tests/fixtures/adversarial/decks.py).

Everything here is made-up content. Nothing in this file writes timing-tree, animation or media play-mode
XML from memory: those come from tests/fixtures/media_modes/ (saved by real PowerPoint) or from the
L010 test's entrance-effect builder, and decks that need anything else say "needs a real-PowerPoint copy".
"""
from __future__ import annotations

import io
import random
import struct
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from tests.fixtures.builders import _embed_fonts, _png, embed, set_timing  # noqa: F401 (re-exported)

HERE = Path(__file__).parent
MEDIA = HERE / "media"
STUBS = Path(__file__).resolve().parents[3] / "engine" / "assets" / "media_stubs"

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
}
NSDECL = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())

WIDE = (13.333, 7.5)
GOOGLE = (10, 5.625)
CANVA = (20, 11.25)
STANDARD = (10, 7.5)

COMMENTS_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
MODERN_RT = "http://schemas.microsoft.com/office/2018/10/relationships/comments"
OLE_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
PACKAGE_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package"
VBA_RT = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"
CONTROL_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/control"


# --- deck and source fingerprints ---------------------------------------------------------------

def new_deck(size=WIDE) -> Presentation:
    prs = Presentation()
    resize(prs, size)
    # Made-up authorship everywhere (public repo).
    prs.core_properties.author = "Sample Presenter"
    prs.core_properties.last_modified_by = "Sample Presenter"
    return prs


def resize(prs, size):
    """Set the slide size and scale the master's and layouts' placeholders with it, as PowerPoint's
    Slide Size ▸ Scale does (python-pptx's template is 10 × 7.5 in)."""
    sx, sy = Inches(size[0]) / prs.slide_width, Inches(size[1]) / prs.slide_height
    prs.slide_width, prs.slide_height = Inches(size[0]), Inches(size[1])
    for el in [m._element for m in prs.slide_masters] + [lay._element for lay in prs.slide_layouts]:
        for off in el.iter(qn("a:off")):
            off.set("x", str(round(int(off.get("x")) * sx)))
            off.set("y", str(round(int(off.get("y")) * sy)))
        for ext in el.iter(qn("a:ext")):
            if ext.get("cx") is not None:
                ext.set("cx", str(round(int(ext.get("cx")) * sx)))
                ext.set("cy", str(round(int(ext.get("cy")) * sy)))


def blank(prs, layout=6):
    return prs.slides.add_slide(prs.slide_layouts[layout])


def _part(prs, name):
    return next(p for p in prs.part.package.iter_parts() if str(p.partname) == name)


def set_app(prs, application="Microsoft Office PowerPoint", version="16.0000"):
    """docProps/app.xml: what X001 and a crew member see under File ▸ Properties."""
    part = _part(prs, "/docProps/app.xml")
    root = etree.fromstring(part.blob)
    ns = root.nsmap.get(None)
    for tag, value in (("Application", application), ("AppVersion", version)):
        el = root.find(f"{{{ns}}}{tag}")
        if tag == "AppVersion" and not value:
            # An empty <AppVersion> makes PowerPoint ask to repair the deck (POWERPOINT_REJECTS.md); leave it out.
            if el is not None:
                root.remove(el)
            continue
        if el is None:
            el = etree.SubElement(root, f"{{{ns}}}{tag}")
        el.text = value
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def set_theme(prs, name=None, major=None, minor=None, colors: dict | None = None):
    """Theme name ('Simple Light' = Google), heading/body fonts, and colour-scheme entries (dk1, lt1, …)."""
    part = _part(prs, "/ppt/theme/theme1.xml")
    root = etree.fromstring(part.blob)
    if name:
        root.set("name", name)
    fs = root.find(".//" + qn("a:fontScheme"))
    for which, face in (("a:majorFont", major), ("a:minorFont", minor)):
        if face:
            fs.find(qn(which)).find(qn("a:latin")).set("typeface", face)
    for key, hexval in (colors or {}).items():
        slot = root.find(".//" + qn("a:clrScheme")).find(qn(f"a:{key}"))
        for c in list(slot):
            slot.remove(c)
        etree.SubElement(slot, qn("a:srgbClr"), val=hexval)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def canva(prs):
    """Canva export fingerprint: 20 × 11.25 in, PowerPoint's app name (Canva writes it), no p14 tags."""
    resize(prs, CANVA)
    set_app(prs, "Microsoft Office PowerPoint", "16.0000")


def google(prs):
    resize(prs, GOOGLE)
    set_app(prs, "", "")
    set_theme(prs, name="Simple Light")


def old_office(prs, version="14.0000"):
    """Office 2007 (12) / 2010 (14): 4:3, Calibri/Cambria, 'Office Theme'."""
    resize(prs, STANDARD)
    set_app(prs, "Microsoft Office PowerPoint", version)
    set_theme(prs, name="Office Theme", major="Calibri", minor="Calibri")


def keynote(prs):
    """Keynote export: Keynote layout names (X001 needs two), Helvetica Neue / Avenir, empty app.xml."""
    set_app(prs, "", "")
    for layout, new in zip(prs.slide_layouts, ("Title & Subtitle", "Title & Bullets", "Title & Photo")):
        layout.name = new


def google_names(slide, page=1):
    """Google Slides names every shape 'Google Shape;<id>;p<page>'."""
    for n, sh in enumerate(slide.shapes, 1):
        sh.name = f"Google Shape;{50 + n};p{page}"


def save(prs, path: Path) -> Path:
    prs.save(str(path))
    return path


# --- text ---------------------------------------------------------------------------------------

def text(slide_or_shapes, txt="Sample text", x=1, y=1, w=4, h=1, font=None, size=None, bold=None, italic=None,
         color=None, name=None, wrap=True, autofit=None, align=None, ea=None, cs=None, sym=None, lang=None):
    shapes = getattr(slide_or_shapes, "shapes", slide_or_shapes)
    tb = shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = wrap
    lines = txt.split("\n")
    tf.text = lines[0]
    for line in lines[1:]:
        tf.add_paragraph().text = line
    for p in tf.paragraphs:
        if align:
            p.alignment = align
        for run in p.runs:
            f = run.font
            if font:
                f.name = font
            if size:
                f.size = Pt(size)
            if bold is not None:
                f.bold = bold
            if italic is not None:
                f.italic = italic
            if color:
                f.color.rgb = RGBColor.from_string(color)
            rpr = run._r.get_or_add_rPr()
            for tag, face in (("a:ea", ea), ("a:cs", cs), ("a:sym", sym)):
                if face:
                    _ordered_font(rpr, tag, face)
            if lang:
                rpr.set("lang", lang)
    body = tf._txBody.find(qn("a:bodyPr"))
    if autofit:
        for c in list(body):
            if c.tag in (qn("a:spAutoFit"), qn("a:normAutofit"), qn("a:noAutofit")):
                body.remove(c)
        body.append(etree.fromstring(f'<a:{autofit} xmlns:a="{NS["a"]}"/>') if "<" not in autofit
                    else etree.fromstring(autofit))
    if name:
        tb.name = name
    return tb


def _ordered_font(rpr, tag, face):
    """a:latin, a:ea, a:cs, a:sym must appear in that order inside a:rPr."""
    order = [qn("a:latin"), qn("a:ea"), qn("a:cs"), qn("a:sym")]
    el = rpr.find(qn(tag))
    if el is None:
        el = etree.SubElement(rpr, qn(tag))
        later = [c for c in rpr if c.tag in order and order.index(c.tag) > order.index(qn(tag))]
        if later:
            later[0].addprevious(el)
    el.set("typeface", face)
    return el


def fill(shape, hexval):
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(hexval)


def background(slide, hexval):
    """A solid slide background (p:bg) in this colour."""
    csld = slide._element.cSld
    old = csld.find(qn("p:bg"))
    if old is not None:
        csld.remove(old)
    bg = etree.fromstring(f'<p:bg {NSDECL}><p:bgPr><a:solidFill><a:srgbClr val="{hexval}"/></a:solidFill>'
                          f'<a:effectLst/></p:bgPr></p:bg>')
    csld.insert(0, bg)


def body_pr(shape, **attrs):
    bp = shape.text_frame._txBody.find(qn("a:bodyPr"))
    for k, v in attrs.items():
        bp.set(k, str(v))
    return bp


def xfrm(shape, **attrs):
    x = shape._element.spPr.find(qn("a:xfrm"))
    for k, v in attrs.items():
        x.set(k, str(v))
    return x


# --- pictures -----------------------------------------------------------------------------------

def png(w=4, h=4):
    return _png(w, h)


def noise_jpeg(w, h, quality=90, seed=1) -> bytes:
    from PIL import Image
    rnd = random.Random(seed)
    im = Image.frombytes("RGB", (w, h), rnd.randbytes(w * h * 3))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)
    return out.getvalue()


def flat_png(w, h, rgba=(200, 30, 30, 255)) -> bytes:
    from PIL import Image
    im = Image.new("RGBA", (w, h), rgba)
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def emf(w=200, h=100) -> bytes:
    """A minimal EMF: EMR_HEADER (bounds, frame, ' EMF' signature) + EMR_EOF."""
    hdr = struct.pack("<II", 1, 108) + struct.pack("<4i", 0, 0, w, h) + struct.pack("<4i", 0, 0, w * 26, h * 26)
    hdr += b" EMF" + struct.pack("<IIHHIII", 0x10000, 108 + 20, 2, 0, 0, 0, 0)
    hdr += struct.pack("<2i", 1920, 1080) + struct.pack("<2i", 508, 285)
    hdr += b"\0" * (108 - len(hdr))
    eof = struct.pack("<IIIII", 14, 20, 0, 16, 20)
    return hdr + eof


def wmf(w=200, h=100) -> bytes:
    """Placeable WMF header (0x9AC6CDD7) + a minimal METAHEADER + EOF record."""
    words = [0, 0, 0, w, h, 1440, 0, 0]
    head = struct.pack("<I", 0x9AC6CDD7) + struct.pack("<HhhhhHI", 0, 0, 0, w, h, 1440, 0)
    checksum = 0
    for i in range(0, len(head), 2):
        checksum ^= struct.unpack("<H", head[i:i + 2])[0]
    head += struct.pack("<H", checksum)
    meta = struct.pack("<HHHIHIH", 1, 9, 0x300, 12, 0, 3, 0)
    return head + meta + struct.pack("<IH", 3, 0)


def tiff(w=64, h=64) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 60)).save(out, "TIFF")
    return out.getvalue()


def picture(slide_or_shapes, blob=None, x=1, y=1, w=2, h=2, name=None):
    shapes = getattr(slide_or_shapes, "shapes", slide_or_shapes)
    pic = shapes.add_picture(io.BytesIO(blob or png()), Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        pic.name = name
    return pic


def retype_image(pic, content_type, ext):
    """Change the declared type and extension of a picture's part (PowerPoint goes by the declared type)."""
    part = pic.part.related_part(pic._element.blip_rId)
    part._content_type = content_type
    part.partname = PackURI(str(part.partname).rsplit(".", 1)[0] + "." + ext)
    return part


def link_picture(slide, target, x=1, y=1, w=3, h=2, name="Linked picture"):
    """A picture whose image is a linked file (r:link), as PowerPoint writes 'Link to File'."""
    pic = picture(slide, x=x, y=y, w=w, h=h, name=name)
    blip = pic._element.find(".//" + qn("a:blip"))
    r_id = slide.part.relate_to(target, RT.IMAGE, is_external=True)
    del blip.attrib[qn("r:embed")]
    blip.set(qn("r:link"), r_id)
    return pic


# --- links --------------------------------------------------------------------------------------

def hyperlink_run(shape, target, action=None):
    """Make the first run a hyperlink (external target) or an action link (internal, no target)."""
    run = shape.text_frame.paragraphs[0].runs[0]
    rpr = run._r.get_or_add_rPr()
    h = etree.SubElement(rpr, qn("a:hlinkClick"))
    if target is not None:
        h.set(qn("r:id"), shape.part.relate_to(target, RT.HYPERLINK, is_external=True))
    else:
        h.set(qn("r:id"), "")
    if action:
        h.set("action", action)
    return h


def jump_to_slide(shape, target_slide):
    """An 'action: jump to slide' link (internal relationship)."""
    run = shape.text_frame.paragraphs[0].runs[0]
    rpr = run._r.get_or_add_rPr()
    h = etree.SubElement(rpr, qn("a:hlinkClick"))
    h.set(qn("r:id"), shape.part.relate_to(target_slide.part, RT.SLIDE))
    h.set("action", "ppaction://hlinksldjump")
    return h


# --- slide show settings (presProps) and transitions --------------------------------------------

def show_pr(prs, inner="", **attrs):
    """Replace <p:showPr> in presProps.xml. `inner`: child XML (p:kiosk, p:browse, p:sldRg, p:custShow …)."""
    part = _part(prs, "/ppt/presProps.xml")
    root = etree.fromstring(part.blob)
    old = root.find(qn("p:showPr"))
    if old is not None:
        root.remove(old)
    a = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    el = etree.fromstring(f'<p:showPr {NSDECL} {a}>{inner}</p:showPr>')
    root.insert(0, el)
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def transition(slide, inner="", **attrs):
    """A plain <p:transition> (ECMA-376 form, no p14 AlternateContent)."""
    root = slide._element
    old = root.find(qn("p:transition"))
    if old is not None:
        root.remove(old)
    a = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    el = etree.fromstring(f'<p:transition {NSDECL} {a}>{inner}</p:transition>')
    anchor = root.find(qn("p:clrMapOvr"))
    (anchor if anchor is not None else root.find(qn("p:cSld"))).addnext(el)
    return el


def custom_show(prs, name, slides):
    """<p:custShowLst> in presentation.xml with one custom show of these slides."""
    pres = prs.part._element
    lst = pres.find(qn("p:custShowLst"))
    if lst is None:
        lst = etree.SubElement(pres, qn("p:custShowLst"))
        anchor = pres.find(qn("p:defaultTextStyle"))
        if anchor is not None:
            anchor.addprevious(lst)
    cs = etree.SubElement(lst, qn("p:custShow"), name=name, id="0")
    sl = etree.SubElement(cs, qn("p:sldLst"))
    for s in slides:
        etree.SubElement(sl, qn("p:sld"), {qn("r:id"): prs.part.relate_to(s.part, RT.SLIDE)})


# --- entrance animations (same XML as tests/checks/test_L010_builds_and_crowds.py) ----------------

def entrance_on_click(slide, shape_ids, preset_class="entr"):
    """Each shape appears (entr) or disappears (exit) on its own click."""
    pars = "".join(
        f'<p:par><p:cTn id="{10 + i * 3}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{11 + i * 3}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{12 + i * 3}" presetID="10" presetClass="{preset_class}" presetSubtype="0" fill="hold" nodeType="clickEffect">'
        f'<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:set><p:cBhvr><p:cTn id="{100 + i}" dur="1" fill="hold"/>'
        f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        f'</p:cBhvr><p:to><p:strVal val="{"visible" if preset_class == "entr" else "hidden"}"/></p:to></p:set></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
        f'</p:childTnLst></p:cTn></p:par>'
        for i, sid in enumerate(shape_ids))
    xml = (f'<p:timing {NSDECL}><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
           f'<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
           f'<p:childTnLst>{pars}</p:childTnLst></p:cTn></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>')
    root = slide._element
    anchor = root.find(qn("p:transition"))
    if anchor is None:
        anchor = root.find(qn("p:clrMapOvr"))
    anchor.addnext(etree.fromstring(xml))


# --- media --------------------------------------------------------------------------------------

def video(slide_or_shapes, data=None, x=1, y=1, w=6, h=3.4, mime="video/mp4", ext="mp4"):
    shapes = getattr(slide_or_shapes, "shapes", slide_or_shapes)
    data = data if data is not None else (STUBS / "stub.mp4").read_bytes()
    mov = shapes.add_movie(io.BytesIO(data), Inches(x), Inches(y), Inches(w), Inches(h), mime_type=mime)
    if ext != "mp4":
        rename_media(mov, ext)
    return mov


def rename_media(pic, ext, content_type=None):
    """Give an embedded media part another extension (python-pptx names every movie .mp4)."""
    part = pic.part
    for rel in part.rels.values():
        if not rel.is_external and str(rel.target_part.partname).startswith("/ppt/media/media"):
            mp = rel.target_part
            if mp.content_type.startswith(("video", "audio")):
                mp.partname = PackURI(str(mp.partname).rsplit(".", 1)[0] + "." + ext)
                if content_type:
                    mp._content_type = content_type


def as_audio(pic):
    """Turn a python-pptx movie into an audio clip: a:audioFile instead of a:videoFile."""
    vf = pic._element.find(".//" + qn("a:videoFile"))
    vf.tag = qn("a:audioFile")
    return pic


def media_trim(pic, start_ms=None, end_ms=None):
    """p14:trim on the media extension (Trim Video's start/end)."""
    media = pic._element.find(".//{%s}media" % NS["p14"])
    t = etree.SubElement(media, "{%s}trim" % NS["p14"])
    if start_ms is not None:
        t.set("st", str(start_ms))
    if end_ms is not None:
        t.set("end", str(end_ms))
    media.insert(0, t)
    return t


def unembed_and_link(slide, pic, target):
    """Linked media: a:videoFile/a:audioFile r:link to an external target, no embedded copy."""
    vf = pic._element.find(".//" + qn("a:videoFile"))
    if vf is None:
        vf = pic._element.find(".//" + qn("a:audioFile"))
    r_id = slide.part.relate_to(target, RT.VIDEO, is_external=True)
    vf.set(qn("r:link"), r_id)
    for ext in list(pic._element.iter("{%s}media" % NS["p14"])):
        ext.getparent().getparent().remove(ext.getparent())


# --- OLE, comments, extra parts -----------------------------------------------------------------

def add_part(prs, source_part, partname, content_type, reltype, blob=b"x"):
    part = Part(PackURI(partname), content_type, prs.part.package, blob)
    return source_part.relate_to(part, reltype), part


def next_id(slide) -> int:
    return max(int(e.get("id")) for e in slide._element.iter(qn("p:cNvPr"))) + 1 if \
        list(slide._element.iter(qn("p:cNvPr"))) else 2


def ole_object(prs, slide, prog_id, name, *, link_target=None, x=1, y=1, w=3, h=2, blob=b"OLE-STAND-IN"):
    """An OLE graphic frame (embedded part, or a linked file when link_target is set) with a preview picture."""
    if link_target:
        r_id = slide.part.relate_to(link_target, OLE_RT, is_external=True)
        attrs = f'progId="{prog_id}" r:id="{r_id}"'
        kind = '<p:link updateAutomatic="1"/>'
    else:
        n = sum(1 for p in prs.part.package.iter_parts() if "embeddings" in str(p.partname)) + 1
        r_id, _ = add_part(prs, slide.part, f"/ppt/embeddings/oleObject{n}.bin",
                           "application/vnd.openxmlformats-officedocument.oleObject", OLE_RT, blob)
        attrs = f'progId="{prog_id}" r:id="{r_id}"'
        kind = '<p:embed/>'
    sid = next_id(slide)
    pic_id = slide.part.relate_to(_preview_part(prs), RT.IMAGE)
    e = lambda v: Emu(Inches(v))
    xml = (f'<p:graphicFrame {NSDECL}><p:nvGraphicFramePr><p:cNvPr id="{sid}" name="{name}"/><p:cNvGraphicFramePr>'
           f'<a:graphicFrameLocks noChangeAspect="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
           f'<p:xfrm><a:off x="{e(x)}" y="{e(y)}"/><a:ext cx="{e(w)}" cy="{e(h)}"/></p:xfrm><a:graphic>'
           f'<a:graphicData uri="http://schemas.openxmlformats.org/presentationml/2006/ole">'
           f'<p:oleObj {attrs} imgW="914400" imgH="609600">{kind}'
           f'<p:pic><p:nvPicPr><p:cNvPr id="0" name=""/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill>'
           f'<a:blip r:embed="{pic_id}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>'
           f'<a:xfrm><a:off x="{e(x)}" y="{e(y)}"/><a:ext cx="{e(w)}" cy="{e(h)}"/></a:xfrm>'
           f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic></p:oleObj></a:graphicData></a:graphic>'
           f'</p:graphicFrame>')
    slide.shapes._spTree.append(etree.fromstring(xml))


_PREVIEW = {}


def _preview_part(prs):
    from pptx.parts.image import ImagePart
    key = id(prs)
    if key not in _PREVIEW:
        _PREVIEW[key] = ImagePart.new(prs.part.package, _image(png(8, 6)))
    return _PREVIEW[key]


def _image(blob):
    from pptx.parts.image import Image
    return Image.from_blob(blob)


def legacy_comment(prs, slide, text_="Can we check this number?", author_id=0, n=1):
    authors = getattr(prs, "_adv_authors", None)
    if authors is None:
        xml = (f'<p:cmAuthorLst {NSDECL}><p:cmAuthor id="0" name="Reviewer One" initials="R1" lastIdx="9" clrIdx="0"/>'
               f'</p:cmAuthorLst>').encode()
        add_part(prs, prs.part, "/ppt/commentAuthors.xml",
                 "application/vnd.openxmlformats-officedocument.presentationml.commentAuthors+xml",
                 "http://schemas.openxmlformats.org/officeDocument/2006/relationships/commentAuthors", xml)
        prs._adv_authors = True
    xml = (f'<p:cmLst {NSDECL}><p:cm authorId="{author_id}" dt="2026-09-01T10:00:00.000" idx="1">'
           f'<p:pos x="10" y="10"/><p:text>{text_}</p:text></p:cm></p:cmLst>').encode()
    add_part(prs, slide.part, f"/ppt/comments/comment{n}.xml",
             "application/vnd.openxmlformats-officedocument.presentationml.comments+xml", COMMENTS_RT, xml)


def modern_comment(prs, slide, n=1, status=None, text_="Please swap this photo."):
    """ppt/comments/modernComment_*.xml (PowerPoint 365 threaded comments). `status`: None or 'resolved'."""
    st = f' status="{status}"' if status else ""
    xml = (f'<p188:cmLst xmlns:p188="http://schemas.microsoft.com/office/powerpoint/2018/8/main" '
           f'xmlns:a="{NS["a"]}"><p188:cm id="{{00000000-0000-0000-0000-00000000000{n}}}" '
           f'authorId="{{00000000-0000-0000-0000-0000000000AA}}" created="2026-09-01T10:00:00.000"{st}>'
           f'<p188:txBody><a:bodyPr/><a:p><a:r><a:t>{text_}</a:t></a:r></a:p></p188:txBody></p188:cm></p188:cmLst>').encode()
    add_part(prs, slide.part, f"/ppt/comments/modernComment_{n}.xml", "application/vnd.ms-powerpoint.comments+xml",
             MODERN_RT, xml)
