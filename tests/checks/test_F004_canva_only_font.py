from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import make_deck, text_box


def test_f004_canva_sans_red_including_bold_variant(tmp_path):
    src = make_deck(tmp_path, text_box(font="Canva Sans"), text_box(font="Canva Sans Bold"))
    assert statuses(run_scan(src, "F004"), "F004") == {"Canva Sans": Status.RED}


def test_f004_normal_font_not_flagged(tmp_path):
    src = make_deck(tmp_path, text_box(font="Calibri"), text_box(font="Sans"))
    assert statuses(run_scan(src, "F004"), "F004") == {}
