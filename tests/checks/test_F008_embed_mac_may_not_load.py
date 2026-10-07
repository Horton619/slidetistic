from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import embed, make_deck


def test_f008_compressed_and_restricted_flagged(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Roboto", "regular", "Roboto", compressed=True),
                                      embed("Licensed", "regular", "Licensed", fs_type=0x0002)])
    assert statuses(run_scan(src, "F008"), "F008") == {"Roboto/regular": Status.YELLOW,
                                                       "Licensed/regular": Status.YELLOW}


def test_f008_plain_embed_not_flagged(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Roboto", "regular", "Roboto"),
                                      embed("Roboto", "bold", "Roboto", "Bold", bare_ttf=True)])
    assert statuses(run_scan(src, "F008"), "F008") == {}
