from pptx.opc.constants import RELATIONSHIP_TYPE as RT

from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import make_deck, text_box


def test_x004_local_file_links_red(tmp_path):
    def post(prs):
        prs.slides[0].part.relate_to("C:\\Users\\pat\\Desktop\\budget.xlsx", RT.OLE_OBJECT, is_external=True)
    src = make_deck(tmp_path, text_box("Notes", link="file:///Users/pat/clip.mov"), post=post)
    assert statuses(run_scan(src, "X004"), "X004") == {
        "C:\\Users\\pat\\Desktop\\budget.xlsx": Status.RED, "file:///Users/pat/clip.mov": Status.RED}


def test_x004_web_links_not_flagged(tmp_path):
    src = make_deck(tmp_path, text_box("Site", link="https://example.com/Users/page"))
    assert statuses(run_scan(src, "X004"), "X004") == {}
