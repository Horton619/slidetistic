from tests.checks.helpers import Status, embedded, run_repair, run_scan, statuses
from tests.fixtures.builders import embed, make_deck, text_box


def test_f005_misnamed_embed_rebuilt_from_files(tmp_path):
    src = make_deck(tmp_path, text_box(font="Roboto"), embeds=[
        embed("Roboto", "regular", "Roboto", "Regular"),
        embed("Roboto Bold", "regular", "Roboto", "Bold"),     # Canva: bold file filed as its own family
    ])
    assert statuses(run_scan(src, "F005"), "F005") == {"Roboto Bold": Status.RED}
    result = run_repair(src, "F005")
    assert statuses(result, "F005") == {"Roboto Bold": Status.GREEN_FIXED}
    assert embedded(result.output_path) == {"Roboto": ["regular", "bold"]}


def test_f005_alias_applied_to_file_family(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Calibri (MS) Bold", "regular", "Calibri (MS)", "Bold")])
    result = run_repair(src, "F005")
    assert embedded(result.output_path) == {"Calibri": ["bold"]}


def test_f005_correct_list_not_flagged(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Roboto", "regular", "Roboto"), embed("Roboto", "bold", "Roboto", "Bold")])
    assert statuses(run_scan(src, "F005"), "F005") == {}


def test_f005_unreadable_file_left_in_place(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Roboto", "regular", "Roboto", compressed=True),
                                      embed("Roboto Bold", "regular", "Roboto", "Bold")])
    result = run_repair(src, "F005")
    assert embedded(result.output_path) == {"Roboto": ["regular", "bold"]}
