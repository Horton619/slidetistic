"""Review 2026-10-13 item 1.13: small hardening fixes (crafted decks, links, downloads, font names)."""
import os
import zipfile

import pytest

from engine import cli, report
from engine.core import fonts_catalog, fonts_install, http


def test_deck_that_unpacks_to_an_enormous_xml_part_is_not_opened(tmp_path, monkeypatch):
    deck = tmp_path / "bomb.pptx"
    with zipfile.ZipFile(deck, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("ppt/slides/slide1.xml", b" " * 2_000_000)
    assert cli.unreadable_reason(deck) is None
    monkeypatch.setattr(cli, "XML_PART_MAX", 1_000_000)
    assert "implausible size" in cli.unreadable_reason(deck)


@pytest.mark.parametrize("url,ok", [
    ("https://www.youtube.com/watch?v=x", True),
    ("http://example.com/a", True),
    ("javascript:alert(1)", False),
    ("file:///etc/passwd", False),
    ("https://youtube.com@evil.example/", False),
    ("https:///nohost", False),
    ("\\\\server\\share\\clip.mp4", False),
])
def test_report_links_are_plain_web_addresses_only(url, ok):
    assert report.web_link(url) is ok


def test_report_table_shows_a_bad_link_as_text():
    html = report._table([("URL", "url")], [{"url": "javascript:alert(1)"}, {"url": "https://a.example/"}],
                         link_key="url")
    assert "href='javascript" not in html and "href='https://a.example/'" in html


@pytest.mark.parametrize("name", ["../../evil", "a/b\\c:d", "..hidden", "\x00x"])
def test_collected_font_names_stay_inside_the_folder(tmp_path, name):
    clean = fonts_install.safe_filename(name + ".ttf")
    assert "/" not in clean and "\\" not in clean and not clean.startswith(".")
    assert (tmp_path / clean).resolve().parent == tmp_path.resolve()


def test_download_over_the_size_cap_is_refused(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b"x" * (n if n > 0 else 10)
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda *a, **k: Resp())
    with pytest.raises(http.TooLarge):
        http.get("https://example.invalid/big", max_bytes=100)


def test_publisher_download_must_match_its_pinned_hash(monkeypatch):
    monkeypatch.setattr(http, "get", lambda url, **k: b"not the real zip")
    entry = {**fonts_catalog.lookup("Aptos"), "url": "https://example.invalid/changed.zip"}
    assert entry["sha256"], "the Aptos zip is pinned in rules/font_downloads.yaml"
    with pytest.raises(RuntimeError, match="changed"):
        fonts_install._publisher_files(entry, {"variants": [(400, "normal")]})
    cached = fonts_catalog.cache_dir() / "downloads"
    assert not any(cached.glob("*.zip")) or all(p.read_bytes() != b"not the real zip" for p in cached.glob("*.zip"))


def test_broken_font_link_doesnt_stop_the_installed_list(tmp_path, monkeypatch):
    fonts = tmp_path / "Fonts"
    fonts.mkdir()
    os.symlink(tmp_path / "gone.ttf", fonts / "Gone.ttf")
    monkeypatch.setattr(fonts_install, "font_dirs", lambda: [fonts])
    assert fonts_install.installed()["families"] == set()
