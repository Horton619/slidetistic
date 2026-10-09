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


def pytest_addoption(parser):
    parser.addoption("--update-snapshots", action="store_true",
                     help="corpus: accept current results as the new snapshots (only after David reviews the diff)")
    parser.addoption("--corpus", default=None,
                     help="corpus: folder of real decks (else $SLIDETISTIC_CORPUS, else .corpus-path)")


def corpus_root(config) -> Path | None:
    root = config.getoption("--corpus") or os.environ.get("SLIDETISTIC_CORPUS")
    if not root and CORPUS_PATH_FILE.exists():
        root = CORPUS_PATH_FILE.read_text().strip()
    return Path(root).expanduser() if root else None


def pytest_terminal_summary(terminalreporter, config):
    from tests import test_corpus
    test_corpus.print_summary(terminalreporter)
