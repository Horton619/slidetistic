from tests.checks.helpers import Status, run_repair, run_scan, slide_runs, statuses
from tests.fixtures.builders import make_deck, text_box


def test_f002_calibri_ms_renamed(tmp_path):
    src = make_deck(tmp_path, text_box(font="Calibri (MS)"))
    result = run_repair(src, "F002")
    assert statuses(result, "F002") == {"Calibri (MS)": Status.GREEN_FIXED}
    assert slide_runs(result.output_path) == [("Calibri", None)]


def test_f002_with_f001_gives_calibri_bold_flag(tmp_path):
    src = make_deck(tmp_path, text_box(font="Calibri (MS) Bold"), text_box(font="Calibri (MS)"))
    result = run_repair(src, "F001", "F002")
    assert (slide_runs(result.output_path)) == [("Calibri", "1"), ("Calibri", None)]
    assert result.summary()["red"] == 0


def test_f002_alone_keeps_suffix_for_f001(tmp_path):
    src = make_deck(tmp_path, text_box(font="Calibri (MS) Bold"))
    result = run_repair(src, "F001", "F002", fix={"F002"})
    assert slide_runs(result.output_path) == [("Calibri Bold", None)]


def test_f002_real_calibri_not_flagged(tmp_path):
    src = make_deck(tmp_path, text_box(font="Calibri"))
    assert statuses(run_scan(src, "F002"), "F002") == {}
