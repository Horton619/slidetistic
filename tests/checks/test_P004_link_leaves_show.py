from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import make_deck, picture, text_box


def test_p004_one_finding_per_slide_listing_links(tmp_path):
    src = make_deck(tmp_path, slides=[[text_box("Site", link="https://example.com"), picture(link="https://shop.example.com")],
                                      [text_box("Ref", link="https://pubmed.ncbi.nlm.nih.gov/1/")]])
    found = [(f.slide, f.status, f.evidence["urls"]) for f in run_scan(src, "P004").findings]
    assert found == [(1, Status.YELLOW, ["https://example.com", "https://shop.example.com"]),
                     (2, Status.YELLOW, ["https://pubmed.ncbi.nlm.nih.gov/1/"])]


def test_p004_media_links_and_plain_url_text_not_flagged(tmp_path):
    # Look-alikes: media links (M005/M006) and a URL that's only typed, not clickable.
    src = make_deck(tmp_path, text_box("Clip", link="https://youtu.be/x"), text_box("Visit https://example.com"))
    assert statuses(run_scan(src, "P004"), "P004") == {}
