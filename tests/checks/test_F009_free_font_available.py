"""F009 (David 2026-10-12): missing fonts that the Fontsource catalog lists can be downloaded. Informational
(F007 already reports the font as missing); detect reads only the cached catalog; files are name-checked."""
import io
import json
import os

import pytest

from engine.core import Deck, fonts_catalog, fonts_install, registry
from engine.core.runner import RunConfig, make_context
from tests.fixtures.builders import make_deck, make_ttf, text_box

CATALOG = [{"id": "montserrat", "family": "Montserrat", "type": "google", "weights": [100, 400, 600, 700],
            "styles": ["normal", "italic"]},
           {"id": "contrail-one", "family": "Contrail One", "type": "google", "weights": [400], "styles": ["normal"]}]


def _catalog(fonts=CATALOG):
    path = fonts_catalog.cache_dir() / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched": "2026-10-12T09:00:00", "fonts": fonts}))
    fonts_catalog._load.cache_clear()


def _detect(tmp_path, *shapes):
    check = next(c for c in registry.discover() if c.id == "F009")()
    deck = Deck(make_deck(tmp_path, *shapes))
    return check.detect(deck, make_context(RunConfig()))


def test_a_missing_catalog_font_is_offered_with_the_weights_the_deck_uses(tmp_path):
    _catalog()
    [f] = _detect(tmp_path, text_box("Hi", font="Montserrat", bold=True, name="A"),
                  text_box("Yo", font="Montserrat SemiBold", name="B"))
    assert f.informational and f.subject == "Montserrat"
    assert f.evidence["variants"] == [[600, "normal"], [700, "normal"]]
    assert "Get fonts can install SemiBold, Bold" in f.message


def test_weights_the_family_lacks_are_listed(tmp_path):
    _catalog()
    [f] = _detect(tmp_path, text_box("Hi", font="Contrail One"), text_box("Yo", font="Contrail One", bold=True))
    assert f.evidence["variants"] == [[400, "normal"]] and "Not in this family: Bold" in f.message


@pytest.mark.parametrize("font", ["Calibri", "Canva Sans", "Gotham"])
def test_not_offered_for_office_canva_only_or_uncatalogued_fonts(tmp_path, font):
    _catalog()
    assert _detect(tmp_path, text_box("Hi", font=font)) == []


def test_not_offered_when_already_installed_here(tmp_path):
    _catalog()
    folder = fonts_install.install_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Montserrat-Regular.ttf").write_bytes(make_ttf("Montserrat"))
    assert _detect(tmp_path, text_box("Hi", font="Montserrat")) == []


def test_without_a_cached_catalog_it_says_so_once(tmp_path):
    [f] = _detect(tmp_path, text_box("Hi", font="Montserrat"), text_box("Yo", font="Contrail One"))
    assert f.subject == "catalog" and f.informational


def test_file_check_refuses_misnamed_and_wrong_weight_files():
    assert fonts_install.check_file(make_ttf("Montserrat", "Regular", 400), "Montserrat", 400, "normal") is None
    assert "named" in fonts_install.check_file(make_ttf("Montserrat Thin", "Regular", 400), "Montserrat", 400, "normal")
    assert "weight" in fonts_install.check_file(make_ttf("Montserrat", "Regular", 100), "Montserrat", 400, "normal")
    # Windows-style family names are fine when the weight word matches: "Poppins SemiBold" at 600.
    assert fonts_install.check_file(make_ttf("Poppins SemiBold", "Regular", 600), "Poppins", 600, "normal") is None


def test_install_and_uninstall_stay_in_the_private_folder():
    _catalog()
    data = make_ttf("Montserrat", "Regular", 400)
    [r] = fonts_install.install("Montserrat", [{"weight": 400, "style": "normal", "data": data, "problem": None}])
    assert r["installed"] and r["file"].startswith(os.environ["SLIDETISTIC_FONT_DIR"])
    assert "montserrat" in fonts_install.installed()["families"]
    assert fonts_install.uninstall("Montserrat") == [r["file"]]
    assert not os.path.exists(r["file"])


def test_publisher_fonts_are_found_by_the_decks_name(tmp_path):
    # Microsoft's Aptos download (rules/font_downloads.yaml): no catalog download needed to know about it.
    from engine.core import fonts_catalog
    assert fonts_catalog.lookup("Aptos Display")["source"] == "microsoft_aptos"
    assert fonts_catalog.lookup("aptos")["family"] == "Aptos"


def test_from_an_archive_the_file_named_like_the_deck_wins(tmp_path, monkeypatch):
    """'Aptos' must get Aptos.ttf, not Aptos Display (whose typographic family is also 'Aptos')."""
    import zipfile
    from tests.fixtures.builders import make_ttf
    from engine.core import fonts_catalog
    from fontTools.ttLib import TTFont
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Aptos-Display.ttf", _typo_ttf("Aptos Display", "Aptos"))
        zf.writestr("Aptos.ttf", make_ttf("Aptos"))
    entry = {**fonts_catalog.lookup("Aptos"), "url": "https://example.invalid/pack.zip"}
    cache = fonts_catalog.cache_dir() / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    import hashlib
    (cache / (hashlib.sha1(entry["url"].encode()).hexdigest()[:12] + ".zip")).write_bytes(z.read_bytes())
    [got] = fonts_install._publisher_files(entry, {"variants": [(400, "normal")]})
    assert TTFont(io.BytesIO(got["data"]))["name"].getDebugName(1) == "Aptos"
    [disp] = fonts_install._publisher_files({**entry, "family": "Aptos Display"}, {"variants": [(400, "normal")]})
    assert TTFont(io.BytesIO(disp["data"]))["name"].getDebugName(1) == "Aptos Display"


def _typo_ttf(legacy, typographic):
    from fontTools.ttLib import TTFont
    from tests.fixtures.builders import make_ttf
    f = TTFont(io.BytesIO(make_ttf(legacy)))
    f["name"].setName(typographic, 16, 3, 1, 0x409)
    f["name"].setName("Display", 17, 3, 1, 0x409)
    out = io.BytesIO()
    f.save(out)
    return out.getvalue()


def test_collect_copies_installed_fonts_under_their_real_name(tmp_path):
    """David 2026-10-12: the deck's fonts next to it, readably named (copies of installed / Creative Cloud files)."""
    folder = fonts_install.install_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".4711.otf").write_bytes(make_ttf("Gotham", "Bold", 700))       # obfuscated, like Creative Cloud
    deck = make_deck(tmp_path, text_box("Hi", font="Gotham", bold=True), text_box("Yo", font="Calibri"))
    res = fonts_install.collect(deck, tmp_path / "out")
    copy = tmp_path / "out" / "Gotham Bold.otf"
    assert not copy.is_symlink() and copy.read_bytes() == (folder / ".4711.otf").read_bytes()
    assert [f["name"] for f in res["fonts"]] == ["Gotham Bold"]                 # Office fonts aren't collected
    assert "Gotham Bold" in (tmp_path / "out" / "FONTS.txt").read_text()
