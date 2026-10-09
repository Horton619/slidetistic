from tests.checks.helpers import Status, run_scan, statuses
from tests.fixtures.builders import embed, make_deck


def test_f008_licence_restricted_embed_flagged(tmp_path):
    src = make_deck(tmp_path, embeds=[embed("Licensed", "regular", "Licensed", fs_type=0x0002)])
    assert statuses(run_scan(src, "F008"), "F008") == {"Licensed/regular": Status.YELLOW}


def test_f008_compressed_and_editable_embeds_not_flagged(tmp_path):
    # Corpus 2026-10-09: PowerPoint compresses every embed it saves, so compression alone is normal.
    # fsType 4 (preview & print) and 8 (editable) both allow embedding.
    src = make_deck(tmp_path, embeds=[embed("Roboto", "regular", "Roboto", compressed=True),
                                      embed("Roboto", "bold", "Roboto", "Bold", fs_type=8),
                                      embed("Lato", "regular", "Lato", fs_type=4)])
    assert statuses(run_scan(src, "F008"), "F008") == {}
