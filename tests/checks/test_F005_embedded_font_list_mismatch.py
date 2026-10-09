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


def test_f005_never_renames_an_embed_the_text_still_uses(tmp_path):
    # Corpus 2026-10-09: 'SN Pro 1 Extra-Light' holds a file named SN Pro, and the text uses
    # 'SN Pro 1 Extra-Light'. Re-filing it would cut the text off from a font that works on Windows.
    src = make_deck(tmp_path, text_box(font="SN Pro 1 Extra-Light"),
                    embeds=[embed("SN Pro 1 Extra-Light", "regular", "SN Pro")])
    result = run_repair(src, "F005")
    assert statuses(result, "F005") == {"SN Pro 1 Extra-Light": Status.YELLOW}
    assert embedded(result.output_path) == {"SN Pro 1 Extra-Light": ["regular"]}


def test_f005_bold_file_in_regular_slot_of_same_name_left_alone(tmp_path):
    # Corpus: 'League Spartan' regular slot holds the bold file; moving it would leave regular text without it.
    src = make_deck(tmp_path, text_box(font="League Spartan"),
                    embeds=[embed("League Spartan", "regular", "League Spartan", "Bold")])
    result = run_repair(src, "F005")
    assert statuses(result, "F005") == {"League Spartan": Status.YELLOW}
    assert result.changes == []


def test_f005_canva_pattern_waits_for_f001(tmp_path):
    # Without F001 renaming the text, 'Roboto Bold' must stay filed as 'Roboto Bold'.
    src = make_deck(tmp_path, text_box(font="Roboto Bold"), embeds=[embed("Roboto Bold", "regular", "Roboto", "Bold")])
    assert run_repair(src, "F005").changes == []
    assert embedded(run_repair(src, "F001", "F005").output_path) == {"Roboto": ["bold"]}


def test_f005_explains_exporter_stand_in(tmp_path):
    src = make_deck(tmp_path, text_box(font="Helvetica"), embeds=[embed("Helvetica", "regular", "Arial")])
    [f] = run_scan(src, "F005").findings
    assert f.status == Status.YELLOW and f.evidence["stand_in"] == "Arial"
    assert run_repair(src, "F005").changes == []
