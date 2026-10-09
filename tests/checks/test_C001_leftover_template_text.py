from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import make_deck, table, text_box


def test_c001_red_and_yellow_leftovers(tmp_path):
    src = make_deck(tmp_path, text_box("Click to add title"), text_box("Lorem ipsum dolor"),
                    text_box("Presented by [Speaker Name]"), text_box("Venue: TBD"))
    assert statuses(run_scan(src, "C001"), "C001") == {
        "click to add": Status.RED, "lorem ipsum": Status.RED, "[speaker name]": Status.RED, "tbd": Status.YELLOW}


def test_c001_finds_text_in_tables(tmp_path):
    src = make_deck(tmp_path, table(text="Your text here"))
    assert statuses(run_scan(src, "C001"), "C001") == {"your text here": Status.RED}


def test_c001_real_text_and_empty_placeholders_not_flagged(tmp_path):
    # Look-alikes: 'TBD' inside a word, 'XXL', a normal bracket, and an empty title placeholder.
    src = make_deck(tmp_path, text_box("Sizes S to XXL"), text_box("TBDS team"), text_box("Results [see appendix]"),
                    layout=1)
    assert statuses(run_scan(src, "C001"), "C001") == {}
