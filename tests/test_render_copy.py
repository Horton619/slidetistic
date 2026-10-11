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
