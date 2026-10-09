from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import make_deck, text_box


def test_f011_emoji_flagged(tmp_path):
    src = make_deck(tmp_path, text_box("Launch day 🚀🎉"), text_box("Love it ❤️"))
    assert [f.status for f in run_scan(src, "F011").findings] == [Status.YELLOW, Status.YELLOW]


def test_f011_plain_symbols_not_flagged(tmp_path):
    # Look-alikes: ✓ ✕ → • © are ordinary text symbols, not emoji.
    src = make_deck(tmp_path, text_box("✓ done ✕ todo → next • item © 2026"))
    assert statuses(run_scan(src, "F011"), "F011") == {}
