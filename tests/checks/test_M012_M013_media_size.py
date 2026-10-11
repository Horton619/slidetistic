"""M013 compress pictures (PowerPoint's 150 ppi + delete cropped areas) and M012 video above 1080p."""
import io

import pytest
from PIL import Image
from pptx.oxml.ns import qn

from engine.core import Deck, Status
from tests.checks.helpers import run_repair, run_scan
from tests.fixtures.builders import make_deck, picture


def photo(w, h, fmt="JPEG", alpha=False):
    """Noisy pixels: compresses like a real photo (a flat colour would make every file tiny)."""
    import os
    im = Image.frombytes("RGBA" if alpha else "RGB", (w, h), os.urandom(w * h * (4 if alpha else 3)))
    buf = io.BytesIO()
    im.save(buf, fmt, **({"quality": 95} if fmt == "JPEG" else {}))
    return buf.getvalue()


def picture_sizes(path):
    out = []
    for p in Deck(path).prs.part.package.iter_parts():
        if str(p.partname).startswith("/ppt/media/") and p.content_type in ("image/jpeg", "image/png"):
            with Image.open(io.BytesIO(p.blob)) as im:
                out.append((p.content_type, im.size, im.mode, len(p.blob)))
    return out


def test_m013_pitches_compression_for_a_huge_photo_shown_small(tmp_path):
    src = make_deck(tmp_path, picture(x=1, y=1, w=2, h=1.5, blob=photo(3000, 2250)))
    [f] = run_scan(src, "M013").findings
    assert f.status == Status.YELLOW and f.evidence["saving_pct"] >= 25 and "Compress pictures" in f.message


def test_m013_stays_quiet_when_pictures_are_already_the_right_size(tmp_path):
    src = make_deck(tmp_path, picture(x=0, y=0, w=13.333, h=7.5, blob=photo(1900, 1069)))
    assert run_scan(src, "M013").findings == []


def test_m013_fix_resizes_to_what_a_1080p_screen_shows(tmp_path):
    # 2 in wide on a 13.33 in slide: 2/13.333 of a 2000 px wide slide = 300 px.
    src = make_deck(tmp_path, picture(x=1, y=1, w=2, h=1.5, blob=photo(3000, 2250)))
    result = run_repair(src, "M013")
    assert [f.status for f in result.findings if f.check_id == "M013"] == [Status.GREEN_FIXED]
    [(ctype, size, _, nbytes)] = picture_sizes(result.output_path)
    assert ctype == "image/jpeg" and abs(size[0] - 300) <= 2 and abs(size[1] - 225) <= 2
    assert picture_sizes(src)[0][3] > 10 * nbytes


def test_m013_deletes_cropped_areas_and_keeps_the_visible_part(tmp_path):
    def cropped(shapes):
        pic = picture(x=1, y=1, w=2, h=1.5, blob=photo(3000, 2250))(shapes)
        pic.crop_left, pic.crop_right = 0.25, 0.25          # the middle half shows
        return pic
    src = make_deck(tmp_path, cropped)
    out = run_repair(src, "M013").output_path
    [(_, size, _, _)] = picture_sizes(out)
    assert abs(size[0] - 300) <= 2 and abs(size[1] - 450) <= 2      # visible 1500×2250 → 300×450
    assert not list(Deck(out).slides[0].part._element.iter(qn("a:srcRect")))


def test_m013_keeps_png_transparency(tmp_path):
    src = make_deck(tmp_path, picture(x=1, y=1, w=2, h=2, blob=photo(2400, 2400, "PNG", alpha=True)))
    [(ctype, size, mode, _)] = picture_sizes(run_repair(src, "M013").output_path)
    assert ctype == "image/png" and mode == "RGBA" and size[0] < 400


def test_m013_leaves_a_picture_alone_when_the_slide_background_uses_it_too(tmp_path):
    def also_background(prs):
        slide = prs.slides[0]
        r_id = slide.shapes[0]._element.blip_rId
        bg = slide._element.cSld.get_or_add_bg()
        bg.append(bg.makeelement(qn("p:bgPr"), {}))
        bf = bg[0].makeelement(qn("a:blipFill"), {})
        bf.append(bf.makeelement(qn("a:blip"), {qn("r:embed"): r_id}))
        bf.append(bf.makeelement(qn("a:stretch"), {}))
        bg[0].append(bf)
        bg[0].append(bg[0].makeelement(qn("a:effectLst"), {}))
    src = make_deck(tmp_path, picture(x=1, y=1, w=2, h=1.5, blob=photo(3000, 2250)), post=also_background)
    assert run_scan(src, "M013").findings == []


@pytest.mark.parametrize("px,flagged", [((3840, 2160), True), ((1920, 1080), False), ((1080, 1920), False)])
def test_m012_flags_only_videos_above_1080p(tmp_path, monkeypatch, px, flagged):
    from tests.checks.helpers import CHECKS
    from tests.fixtures.builders import video
    # The registry can load a check module more than once: patch the globals of the code that runs.
    monkeypatch.setitem(CHECKS["M012"].detect.__globals__, "probe",
                        lambda m: {"width": px[0], "height": px[1], "mb": 50.0, "video_codec": "h264"})
    found = run_scan(make_deck(tmp_path, video()), "M012").findings
    assert bool(found) == flagged
    if flagged:
        assert "3840×2160 (4K)" in found[0].message
