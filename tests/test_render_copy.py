"""Render copies (2026-10-11): what PowerPoint is handed has stand-in media; the real deck never changes."""
import os
import zipfile

from engine.core import Deck
from engine.core.deck import stub_for, write_render_copy
from engine.render import content_key
from tests.fixtures.builders import make_deck, text_box, video

BIG = b"\x00\x00\x00\x18ftypmp42" + os.urandom(2_000_000)      # random: doesn't compress, like real video


def media(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: (z.read(i), i.compress_type) for i in z.infolist() if i.filename.startswith("ppt/media/")}


def test_render_copy_swaps_media_and_keeps_everything_else(tmp_path):
    src = make_deck(tmp_path, text_box("Title"), video(data=BIG))
    dst = tmp_path / "render.pptx"
    write_render_copy(src, dst)
    vids = {n: v for n, v in media(dst).items() if n.endswith(".mp4")}
    assert vids and all(len(data) < 10_000 and ctype == zipfile.ZIP_STORED for data, ctype in vids.values())
    with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst) as b:
        others = [n for n in a.namelist() if stub_for(n) is None]
        assert all(a.read(n) == b.read(n) for n in others)          # slides, poster image, rels untouched
    assert dst.stat().st_size < src.stat().st_size / 10


def test_fit_round_save_writes_stand_ins_but_a_normal_save_keeps_the_video(tmp_path):
    deck = Deck(make_deck(tmp_path, video(data=BIG)))
    deck.save(tmp_path / "round.pptx", render_copy=True)
    deck.save(tmp_path / "out.pptx")
    assert max(len(d) for d, _ in media(tmp_path / "round.pptx").values()) < 2_000_000
    assert any(d == BIG for d, _ in media(tmp_path / "out.pptx").values())


def test_content_key_sees_a_render_copy_and_the_real_deck_as_the_same_render(tmp_path):
    src = make_deck(tmp_path, text_box("Title"), video(data=BIG))
    dst = tmp_path / "render.pptx"
    write_render_copy(src, dst)
    assert content_key(src) == content_key(dst)
    other = make_deck(tmp_path, text_box("Other title"), video(data=BIG), name="other.pptx")
    assert content_key(other) != content_key(src)


def test_render_copy_neutralises_links_macros_and_activex(tmp_path):
    """Review 2026-10-13 (1.3/1.5): nothing in a render copy reaches out or runs."""
    import zipfile
    from engine.core.deck import LINK_REMOVED, write_render_copy
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    rels = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
            f'<Relationship Id="rId2" Type="{R}/image" Target="\\\\server\\share\\logo.png" TargetMode="External"/>'
            f'<Relationship Id="rId3" Type="{R}/hyperlink" Target="https://example.com/" TargetMode="External"/>'
            f'<Relationship Id="rId4" Type="{R}/control" Target="../activeX/activeX1.xml"/>'
            f'</Relationships>').encode()
    P = "http://schemas.openxmlformats.org/presentationml/2006/main"
    MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    slide = (f'<p:sld xmlns:p="{P}" xmlns:mc="{MC}"><p:cSld><p:spTree/>'
             f'<mc:AlternateContent><mc:Choice Requires="v14"><p:controls><p:control r:id="rId4" '
             f'xmlns:r="{R}"/></p:controls></mc:Choice><mc:Fallback><p:controls/></mc:Fallback>'
             f'</mc:AlternateContent></p:cSld></p:sld>').encode()
    src, dst = tmp_path / "in.pptx", tmp_path / "out.pptx"
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        z.writestr("ppt/slides/slide1.xml", slide)
        z.writestr("ppt/_rels/presentation.xml.rels", rels.replace(b"/control", b"/vbaProject"))
    write_render_copy(src, dst)
    with zipfile.ZipFile(dst) as z:
        out = z.read("ppt/slides/_rels/slide1.xml.rels").decode()
        s = z.read("ppt/slides/slide1.xml").decode()
        pres = z.read("ppt/_rels/presentation.xml.rels").decode()
    assert "server" not in out and LINK_REMOVED in out
    assert "https://example.com/" in out, "hyperlinks only open on a click: kept"
    assert "rId4" not in out and "slideLayout1" in out
    assert "controls" not in s and "AlternateContent" not in s and "spTree" in s
    assert "vbaProject" not in pres
