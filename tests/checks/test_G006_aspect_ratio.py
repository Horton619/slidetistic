from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import CANVA, GOOGLE, STANDARD, WIDE, make_deck


def test_g006_4x3_flagged(tmp_path):
    result = run_scan(make_deck(tmp_path, size=STANDARD), "G006")
    assert statuses(result, "G006") == {"aspect": Status.YELLOW}
    assert "4:3" in result.findings[0].message


def test_g006_all_16x9_sizes_pass(tmp_path):
    # Look-alikes: PowerPoint, Google and Canva all use different 16:9 sizes.
    for i, size in enumerate((WIDE, GOOGLE, CANVA)):
        assert statuses(run_scan(make_deck(tmp_path, size=size, name=f"d{i}.pptx"), "G006"), "G006") == {}
