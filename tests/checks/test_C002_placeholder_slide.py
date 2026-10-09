from tests.checks.helpers import Status, run_scan
from tests.fixtures.builders import make_deck, picture, text_box


def found(result):
    return [(f.slide, f.subject, f.status) for f in result.findings if f.check_id == "C002"]


def test_c002_video_here_and_empty_slides(tmp_path):
    src = make_deck(tmp_path, slides=[[text_box("VIDEO HERE!")], [], [text_box("Insert video"), picture()]])
    assert found(run_scan(src, "C002")) == [
        (1, "placeholder", Status.RED), (2, "empty", Status.YELLOW), (3, "placeholder", Status.YELLOW)]


def test_c002_layout_with_only_empty_placeholders_counts_as_empty(tmp_path):
    src = make_deck(tmp_path, layout=1)
    assert found(run_scan(src, "C002")) == [(1, "empty", Status.YELLOW)]


def test_c002_real_slides_not_flagged(tmp_path):
    # Look-alike: a slide that mentions a video among real content.
    src = make_deck(tmp_path, slides=[[text_box("Watch the video here, then discuss with your table")], [picture()]])
    assert found(run_scan(src, "C002")) == []


def test_c002_walk_in_slide_with_background_image_is_not_empty(tmp_path):
    # Corpus 2026-10-09: first/last slides are often "empty" but show a full-screen background.
    from pptx.oxml.ns import qn
    def post(prs):
        cSld = prs.slides[0]._element.cSld
        bg = cSld.makeelement(qn("p:bg"), {})
        bg_pr = bg.makeelement(qn("p:bgPr"), {})
        bg_pr.append(bg_pr.makeelement(qn("a:solidFill"), {}))
        bg_pr[0].append(bg_pr.makeelement(qn("a:srgbClr"), {"val": "000000"}))
        bg_pr.append(bg_pr.makeelement(qn("a:effectLst"), {}))
        bg.append(bg_pr)
        cSld.insert(0, bg)
    src = make_deck(tmp_path, post=post)
    assert found(run_scan(src, "C002")) == []
