from tests.checks.helpers import run_scan
from tests.fixtures.builders import make_deck, text_box


def test_c004_hidden_slide_reported(tmp_path):
    src = make_deck(tmp_path, slides=[[text_box("Shown")], [text_box("Backup")]], hidden=[2])
    found = [(f.slide, f.evidence["slide_name"]) for f in run_scan(src, "C004").findings]
    assert found == [(2, "Backup")]


def test_c004_visible_slides_not_flagged(tmp_path):
    src = make_deck(tmp_path, slides=[[text_box("A")], [text_box("B")]])
    assert run_scan(src, "C004").findings == []
