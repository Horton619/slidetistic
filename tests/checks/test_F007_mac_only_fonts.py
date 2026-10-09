from tests.checks.helpers import Status, run_scan
from tests.fixtures.builders import make_deck, text_box


def test_f007_keynote_fonts_get_swap_suggestion(tmp_path):
    src = make_deck(tmp_path, text_box(font="Avenir Next"), text_box(font="Helvetica Neue"))
    found = {f.subject: (f.status, f.evidence["mac_only_swap"]) for f in run_scan(src, "F007").findings}
    assert found == {"Avenir Next": (Status.RED, "Century Gothic"), "Helvetica Neue": (Status.RED, "Arial")}


def test_f007_cloud_and_windows_fonts_are_yellow(tmp_path):
    src = make_deck(tmp_path, text_box(font="Aptos"), text_box(font="Aptos Display"), text_box(font="Segoe UI"),
                    text_box(font="Montserrat"))
    found = {f.subject: f.status for f in run_scan(src, "F007").findings}
    assert found == {"Aptos": Status.YELLOW, "Aptos Display": Status.YELLOW, "Segoe UI": Status.YELLOW,
                     "Montserrat": Status.RED}
