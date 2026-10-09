from tests.checks.helpers import Status, run_scan
from tests.fixtures.builders import make_deck, picture, text_box


def found(result):
    return sorted((f.slide, f.evidence["site"], f.evidence["found_in"]) for f in result.findings if f.check_id == "M006")


def test_m006_links_in_text_notes_and_hyperlinks(tmp_path):
    src = make_deck(tmp_path,
        slides=[[text_box("Play https://youtu.be/abc123 now")], [text_box("Clip", link="https://vimeo.com/42")], [text_box("x")]],
        notes=["", "", "Video file: https://drive.google.com/file/d/XYZ/view and https://example.com/talk.mp4"])
    assert found(run_scan(src, "M006")) == [
        (1, "YouTube", "slide text"), (2, "Vimeo", "hyperlink"),
        (3, "Google Drive", "notes"), (3, "Media file", "notes")]


def test_m006_everything_yellow_with_slide_name(tmp_path):
    src = make_deck(tmp_path, text_box("Opening video"), notes="https://www.dropbox.com/s/abc/clip.mov")
    [f] = [f for f in run_scan(src, "M006").findings if f.check_id == "M006"]
    assert f.status == Status.YELLOW and f.evidence["slide_name"] == "Opening video"


def test_m006_ignores_normal_urls_and_m005_pictures(tmp_path):
    src = make_deck(tmp_path, text_box("See https://example.com/agenda"),
                    picture(link="https://www.youtube.com/watch?v=x"), notes="www.company.com")
    assert found(run_scan(src, "M006")) == []
