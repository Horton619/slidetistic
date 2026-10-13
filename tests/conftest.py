import os
from pathlib import Path

import pytest

from engine.core import registry

REPO = Path(__file__).resolve().parent.parent
DUMMY_DIR = Path(__file__).parent / "dummy_checks"
CORPUS_PATH_FILE = REPO / ".corpus-path"     # git-ignored; one line: the folder holding real decks


@pytest.fixture
def checks_with_dummies():
    return registry.discover([DUMMY_DIR])


def corpus_root(config) -> Path | None:
    root = config.getoption("--corpus") or os.environ.get("SLIDETISTIC_CORPUS")
    if not root and CORPUS_PATH_FILE.exists():
        root = CORPUS_PATH_FILE.read_text().strip()
    return Path(root).expanduser() if root else None


def pytest_terminal_summary(terminalreporter, config):
    from tests import test_corpus
    test_corpus.print_summary(terminalreporter)


@pytest.fixture(autouse=True)
def _private_font_folders(tmp_path_factory, monkeypatch):
    """F009: tests never read this machine's fonts or font cache, and never install anything for real."""
    from engine.core import fonts_catalog
    base = tmp_path_factory.mktemp("fonts")
    monkeypatch.setenv("SLIDETISTIC_FONT_CACHE", str(base / "cache"))
    monkeypatch.setenv("SLIDETISTIC_FONT_DIR", str(base / "installed"))
    fonts_catalog._load.cache_clear()
    yield
    fonts_catalog._load.cache_clear()
