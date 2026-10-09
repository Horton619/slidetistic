import io
import os

from tests.checks.helpers import Status, run_scan
from tests.fixtures.builders import make_deck, picture


def found(result, check_id):
    return [f.status for f in result.findings if f.check_id == check_id]


def noisy_png(w, h):
    """A PNG that stays big on disk (random pixels don't compress), so the MB threshold is met."""
    import zlib, struct
    raw = b"".join(b"\x00" + os.urandom(w * 3) for _ in range(h))
    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def test_m008_huge_photo_shown_small(tmp_path):
    src = make_deck(tmp_path, picture(w=1.3, h=1, blob=noisy_png(1200, 900)))   # ~190 px shown
    assert found(run_scan(src, "M008"), "M008") == [Status.YELLOW]


def test_m008_big_pixels_but_small_file_not_flagged(tmp_path):
    src = make_deck(tmp_path, picture(w=1.3, h=1, px=(1200, 900)))   # flat colour: tiny file
    assert found(run_scan(src, "M008"), "M008") == []


def test_m009_tiny_image_stretched_full_screen(tmp_path):
    src = make_deck(tmp_path, picture(x=0, y=0, w=13.333, h=7.5, px=(640, 360)))
    assert found(run_scan(src, "M009"), "M009") == [Status.YELLOW]


def test_m009_full_hd_image_full_screen_not_flagged(tmp_path):
    src = make_deck(tmp_path, picture(x=0, y=0, w=13.333, h=7.5, px=(1920, 1080)))
    assert found(run_scan(src, "M009"), "M009") == []
