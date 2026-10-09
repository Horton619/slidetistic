from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import make_deck, text_box


def test_x002_emoji_and_long_names(tmp_path):
    src = make_deck(tmp_path, text_box(), name="Keynote 🎤 final:v2 " + "x" * 110 + ".pptx")
    assert statuses(run_scan(src, "X002"), "X002") == {"name-chars": Status.YELLOW, "name-length": Status.YELLOW}


def test_x002_normal_name_not_flagged(tmp_path):
    src = make_deck(tmp_path, text_box(), name="PAT MBD - Session 2 (final).pptx")
    assert statuses(run_scan(src, "X002"), "X002") == {}
