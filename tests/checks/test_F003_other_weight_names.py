from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import embed, make_deck, text_box


def test_f003_weight_of_available_family_flagged_yellow(tmp_path):
    src = make_deck(tmp_path, text_box(font="Montserrat SemiBold"), text_box(font="Lato Light"),
                    embeds=[embed("Montserrat", "regular", "Montserrat")])
    assert statuses(run_scan(src, "F003", crew=["Lato"]), "F003") == {
        "Lato Light": Status.YELLOW, "Montserrat SemiBold": Status.YELLOW}


def test_f003_unavailable_family_left_to_f007(tmp_path):
    src = make_deck(tmp_path, text_box(font="Montserrat SemiBold"))
    result = run_scan(src, "F003", "F007")
    assert statuses(result, "F003") == {}
    assert statuses(result, "F007") == {"Montserrat SemiBold": Status.RED}


def test_f003_office_and_exact_installed_names_not_flagged(tmp_path):
    # Look-alikes: 'Calibri Light' and 'Arial Black' are real Office fonts.
    src = make_deck(tmp_path, text_box(font="Calibri Light"), text_box(font="Arial Black"),
                    text_box(font="Montserrat Medium"))
    assert statuses(run_scan(src, "F003", crew=["Montserrat", "Montserrat Medium"]), "F003") == {}
