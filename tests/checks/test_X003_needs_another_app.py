from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import add_part, make_deck, text_box

VBA_RT = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"


def test_x003_macros_flagged(tmp_path):
    def post(prs):
        add_part(prs, prs.part, "/ppt/vbaProject.bin", "application/vnd.ms-office.vbaProject", VBA_RT)
    src = make_deck(tmp_path, text_box(), post=post)
    assert statuses(run_scan(src, "X003"), "X003") == {"macros": Status.YELLOW}


def test_x003_plain_deck_not_flagged(tmp_path):
    assert statuses(run_scan(make_deck(tmp_path, text_box()), "X003"), "X003") == {}
