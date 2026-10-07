"""Runs automatically against EVERY registered check. Nothing to write per check."""
import hashlib
import re

import pytest

from engine.core import Deck, registry, rules
from engine.core.check import GROUP_LETTERS, GROUPS, SOURCES, Check, Context
from engine.core.runner import RunConfig, make_context, repair
from tests.conftest import DUMMY_DIR
from tests.fixtures.builders import CORNER_DECKS

# X998 crashes on purpose (runner tests use it); every other check must pass every contract.
ALL = [c for c in registry.discover([DUMMY_DIR]) if c.id != "X998"]
FIXERS = [c for c in ALL if not c.report_only]
ids = lambda c: c.id


def test_ids_unique_and_discovery_works():
    found = registry.discover([DUMMY_DIR])
    assert len({c.id for c in found}) == len(found)
    assert {"X999", "X998"} <= {c.id for c in found}


@pytest.mark.parametrize("cls", ALL, ids=ids)
def test_metadata_valid(cls):
    assert re.fullmatch(r"[FGLPMX]\d{3}", cls.id), cls.id
    assert cls.group in GROUPS
    assert GROUP_LETTERS[cls.id[0]] == cls.group, f"{cls.id} is in group {cls.group}"
    assert cls.title and cls.description
    assert set(cls.sources) <= SOURCES
    known = set(rules.load("thresholds"))
    assert set(cls.thresholds) <= known, f"missing in thresholds.yaml: {set(cls.thresholds) - known}"
    all_ids = {c.id for c in registry.discover([DUMMY_DIR])}
    assert set(cls.runs_after) <= all_ids
    if cls.report_only:
        assert cls.fix is Check.fix, "report_only checks must not define fix()"


@pytest.mark.parametrize("deck_name", CORNER_DECKS)
@pytest.mark.parametrize("cls", ALL, ids=ids)
def test_detect_is_read_only_and_survives(cls, deck_name, tmp_path):
    deck = Deck(CORNER_DECKS[deck_name](tmp_path))
    before = deck.part_blobs()
    findings = cls().detect(deck, make_context(RunConfig()))
    assert deck.part_blobs() == before, "detect() changed the deck"
    assert all(f.check_id == cls.id for f in findings)


@pytest.mark.parametrize("deck_name", CORNER_DECKS)
@pytest.mark.parametrize("cls", FIXERS, ids=ids)
def test_fix_is_scoped_idempotent_and_leaves_input_alone(cls, deck_name, tmp_path):
    src = CORNER_DECKS[deck_name](tmp_path)
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    config = RunConfig(checks={cls.id}, fixes={cls.id})

    first = repair(src, [cls], config, tmp_path / "once.pptx")
    assert hashlib.sha256(src.read_bytes()).hexdigest() == digest, "input file was modified"

    flagged = {(f.slide, f.shape_id) for f in cls().detect(Deck(src), make_context(config))}
    for change in first.changes:
        assert (change.slide, change.shape_id) in flagged, f"fix touched an unflagged shape: {change}"

    second = repair(first.output_path, [cls], config, tmp_path / "twice.pptx")
    assert second.changes == [], "fix is not idempotent"
