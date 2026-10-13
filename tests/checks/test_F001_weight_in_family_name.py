from tests.checks.helpers import Status, run_repair, run_scan, slide_runs, statuses
from tests.fixtures.builders import embed, make_deck, text_box


def test_f001_bold_suffix_fixed_to_family_plus_bold(tmp_path):
    src = make_deck(tmp_path, text_box("Title", font="Roboto Bold"), text_box("Body", font="Roboto"))
    assert statuses(run_scan(src, "F001"), "F001") == {"Roboto Bold": Status.RED}
    result = run_repair(src, "F001")
    assert statuses(result, "F001") == {"Roboto Bold": Status.GREEN_FIXED}
    assert (slide_runs(result.output_path)) == [("Roboto", "1"), ("Roboto", None)]


def test_f001_bold_italic_and_office_base(tmp_path):
    src = make_deck(tmp_path, text_box(font="Arial Bold Italic"))
    result = run_repair(src, "F001")
    assert statuses(result, "F001") == {"Arial Bold Italic": Status.GREEN_FIXED}
    assert slide_runs(result.output_path) == [("Arial", "1")]


def test_f001_base_known_only_from_embedded_file(tmp_path):
    src = make_deck(tmp_path, text_box(font="Poppins Bold"), embeds=[embed("Poppins Bold", "regular", "Poppins", "Bold")])
    assert statuses(run_scan(src, "F001"), "F001") == {"Poppins Bold": Status.RED}


def test_f001_embedded_name_that_cant_be_refiled_is_left_alone(tmp_path):
    # Dealer Trust 2026-10-12 (Canva): 'Arial Nova Condensed Bold' is embedded, but its file says family
    # 'Arial Nova', so F005 can't refile it under 'Arial Nova Condensed'. Renaming made the text regular.
    src = make_deck(tmp_path, text_box("A", font="Arial Nova Condensed Bold"), text_box("B", font="Arial Nova Condensed"),
                    embeds=[embed("Arial Nova Condensed Bold", "regular", "Arial Nova", "Condensed Bold", weight=700),
                            embed("Arial Nova Condensed", "regular", "Arial Nova", "Condensed")])
    result = run_repair(src, "F001")
    [f] = [f for f in result.findings if f.check_id == "F001"]
    assert f.is_note and result.changes == []


def test_f001_office_base_embedded_as_written_is_still_renamed(tmp_path):
    # PAT 2026-10-06: 'Calibri Bold' embedded under that name; real Calibri Bold is on every machine.
    src = make_deck(tmp_path, text_box(font="Calibri Bold"), embeds=[embed("Calibri Bold", "regular", "Calibri", "Bold")])
    assert statuses(run_scan(src, "F001"), "F001") == {"Calibri Bold": Status.RED}


def test_f001_real_family_ending_in_bold_is_left_alone(tmp_path):
    # Nearest look-alike: 'Arial Rounded MT Bold' is a real font; there's no 'Arial Rounded MT'.
    src = make_deck(tmp_path, text_box(font="Arial Rounded MT Bold"))
    result = run_repair(src, "F001")
    assert statuses(result, "F001") == {"Arial Rounded MT Bold": Status.YELLOW}
    assert result.changes == []


def test_f001_plain_family_not_flagged(tmp_path):
    src = make_deck(tmp_path, text_box(font="Roboto"), text_box(font="Calibri", bold=True))
    assert statuses(run_scan(src, "F001"), "F001") == {}


def test_f001_extra_bold_is_not_bold(tmp_path):
    # Dropbox corpus 2026-10-09: 'Tilda Sans Extra Bold' must not become 'Tilda Sans Extra' + bold.
    src = make_deck(tmp_path, text_box(font="Tilda Sans Extra Bold"), text_box(font="Tilda Sans"),
                    text_box(font="DIN 2014 Narrow Semi Bold"))
    assert statuses(run_scan(src, "F001"), "F001") == {}
    assert set(statuses(run_scan(src, "F003", crew=["Tilda Sans", "DIN 2014 Narrow"]), "F003")) == {
        "Tilda Sans Extra Bold", "DIN 2014 Narrow Semi Bold"}


def test_f001_doubled_style_word_fixed_in_one_repair(tmp_path):
    # AACS corpus 2026-10-10 (Canva export): 'Barlow Bold Bold' took two repairs (→ 'Barlow Bold' → 'Barlow').
    src = make_deck(tmp_path, text_box("A", font="Barlow Bold Bold"), text_box("B", font="Barlow"))
    result = run_repair(src, "F001")
    assert statuses(result, "F001") == {"Barlow Bold Bold": Status.GREEN_FIXED}
    assert slide_runs(result.output_path) == [("Barlow", "1"), ("Barlow", None)]
    again = result.output_path.with_name("again.pptx")
    result.output_path.replace(again)
    assert run_repair(again, "F001").changes == []
