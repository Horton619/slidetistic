from pathlib import Path

import pytest

from engine.core import registry

DUMMY_DIR = Path(__file__).parent / "dummy_checks"


@pytest.fixture
def checks_with_dummies():
    return registry.discover([DUMMY_DIR])
