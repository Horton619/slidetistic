from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import add_part, make_deck, text_box

COMMENTS_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
MODERN_RT = "http://schemas.microsoft.com/office/2018/10/relationships/comments"


def test_c007_classic_and_modern_comments(tmp_path):
    def post(prs):
        add_part(prs, prs.slides[0].part, "/ppt/comments/comment1.xml",
                 "application/vnd.openxmlformats-officedocument.presentationml.comments+xml", COMMENTS_RT)
        add_part(prs, prs.slides[1].part, "/ppt/comments/modernComment_1.xml",
                 "application/vnd.ms-powerpoint.comments+xml", MODERN_RT)
    src = make_deck(tmp_path, slides=[[text_box("A")], [text_box("B")]], post=post)
    [f] = run_scan(src, "C007").findings
    assert (f.status, f.evidence["slides"]) == (Status.YELLOW, [1, 2]) and "1–2" in f.message


def test_c007_no_comments_not_flagged(tmp_path):
    assert statuses(run_scan(make_deck(tmp_path, text_box("A"), notes="speaker notes"), "C007"), "C007") == {}
