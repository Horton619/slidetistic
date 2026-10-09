from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from tests.checks.helpers import Status, run_scan
from tests.fixtures.builders import make_deck, picture, text_box

YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def findings(result):
    return [(f.slide, f.subject, f.status) for f in result.findings if f.check_id == "M005"]


def test_m005_google_style_picture_linking_to_youtube(tmp_path):
    src = make_deck(tmp_path, slides=[[text_box("Intro")], [picture(link=YT)]])
    result = run_scan(src, "M005")
    assert findings(result) == [(2, YT, Status.RED)]
    assert result.findings[0].evidence["slide_name"] == "Slide 2"


def test_m005_streaming_player_relationship(tmp_path):
    def post(prs):
        prs.slides[0].part.relate_to("https://player.vimeo.com/video/123", RT.VIDEO, is_external=True)
    src = make_deck(tmp_path, text_box("Watch"), post=post)
    assert findings(run_scan(src, "M005")) == [(1, "https://player.vimeo.com/video/123", Status.RED)]


def test_m005_text_link_and_non_video_picture_link_not_flagged(tmp_path):
    # Look-alikes: a YouTube link in text (M006's job) and a picture linking to a normal site (P004's).
    src = make_deck(tmp_path, text_box("Video", link=YT), picture(link="https://example.com"))
    assert findings(run_scan(src, "M005")) == []
