"""The PAT MBD pattern end to end, built in code until the real deck is in the corpus."""
from tests.checks.helpers import embedded, font_parts, run_repair, slide_runs
from tests.fixtures.builders import embed, make_deck, text_box

FONT_CHECKS = ["F001", "F002", "F003", "F004", "F005", "F006", "F007", "F008"]


def test_pat_like_canva_deck(tmp_path):
    src = make_deck(tmp_path,
                    text_box("Title", font="Calibri (MS) Bold"), text_box("Body", font="Calibri (MS)"),
                    text_box("Quote", font="Roboto Bold"), text_box("Note", font="Roboto"),
                    embeds=[embed("Calibri (MS)", "regular", "Calibri (MS)"),
                            embed("Calibri (MS) Bold", "regular", "Calibri (MS)", "Bold"),
                            embed("Roboto", "regular", "Roboto", compressed=True),
                            embed("Roboto Bold", "regular", "Roboto", "Bold")])
    result = run_repair(src, *FONT_CHECKS)
    out = result.output_path

    assert (slide_runs(out)) == [("Calibri", "1"), ("Calibri", None), ("Roboto", "1"), ("Roboto", None)]
    assert embedded(out) == {"Roboto": ["regular", "bold"]}
    assert len(font_parts(out)) == 2
    s = result.summary()
    assert (s["red"], s["tool_error"]) == (0, 0)
    # Only the compressed Roboto regular remains, as a yellow "install it" note (F008, report-only).
    assert [(f.check_id, f.subject) for f in result.findings if f.status.value == "yellow"] == [("F008", "Roboto/regular")]
