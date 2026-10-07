from tests.checks.helpers import Status, embedded, font_parts, run_repair, run_scan, statuses
from tests.fixtures.builders import embed, make_deck


def test_f006_calibri_embed_dropped_with_its_file(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Calibri", "regular", "Calibri"), embed("Roboto", "regular", "Roboto")])
    assert statuses(run_scan(src, "F006"), "F006") == {"Calibri": Status.YELLOW}
    result = run_repair(src, "F006")
    assert statuses(result, "F006") == {"Calibri": Status.GREEN_FIXED}
    assert embedded(result.output_path) == {"Roboto": ["regular"]}
    assert len(font_parts(result.output_path)) == 1


def test_f006_last_embed_removed_removes_list(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Calibri", "regular", "Calibri")])
    result = run_repair(src, "F006")
    assert embedded(result.output_path) == {} and font_parts(result.output_path) == []


def test_f006_non_office_embed_kept(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Roboto", "regular", "Roboto")])
    assert statuses(run_scan(src, "F006"), "F006") == {}
