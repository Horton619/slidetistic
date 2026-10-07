from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import embed, make_deck, text_box


def test_f007_unembedded_non_office_font_red(tmp_path):
    src = make_deck(tmp_path, text_box(font="Montserrat"), text_box(font="Montserrat Bold"))
    assert statuses(run_scan(src, "F007"), "F007") == {"Montserrat": Status.RED}


def test_f007_covered_fonts_not_flagged(tmp_path):
    src = make_deck(tmp_path, text_box(font="Calibri (MS) Bold"), text_box(font="Roboto"),
                    text_box(font="Poppins"), text_box(font="Canva Sans"),
                    embeds=[embed("Roboto", "regular", "Roboto")])
    # Calibri (MS) Bold → Calibri (Office); Roboto embedded; Poppins on crew list; Canva Sans → F004.
    assert statuses(run_scan(src, "F007", crew=["Poppins"]), "F007") == {}
