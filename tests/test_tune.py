"""`slidetistic tune` (David 2026-10-11): votes → report, proposals replayed against the votes, questions,
and --apply writing an approved proposal into rules/tuning.yaml."""
import json
import shutil
from types import SimpleNamespace

from engine import tune
from engine.core import rules, tuning


def _vote(i, vote, move, reason=None, check="L008", fix="move", t="2026-10-12T01:00:00", **extra):
    change = {"shape_id": 2, "check": check, "fix": fix, "move_in": move, "width_pct": 0.0, "font_pct": 0.0,
              "spacing_pct": 0.0, "role": "body", "severity": "yellow", "past_border_in": move, **extra}
    return {"t": t, "deck_sha12": f"deck{i:03d}", "slide": 1, "tuning_sig": f"s{i}", "vote": vote,
            "reason": reason, "changes": [change], "diff_pct": move * 3}


def _votes():
    small = [_vote(i, "down", 0.02 + i / 100, "not_worth") for i in range(5)]
    big = [_vote(10 + i, "up", 0.4 + i / 10) for i in range(4)]
    return small + big


def _write(folder, rows, machine="mac"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"votes-{machine}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_latest_vote_wins_and_clear_removes(tmp_path):
    _write(tmp_path, [_vote(1, "down", 0.1), _vote(1, "up", 0.1, t="2026-10-12T02:00:00"),
                      _vote(2, "up", 0.1), _vote(2, "clear", 0.1, t="2026-10-12T02:00:00")])
    votes = tune.load_votes(tmp_path)
    assert [(v["deck_sha12"], v["vote"]) for v in votes] == [("deck001", "up")]


def test_proposes_a_size_threshold_that_spares_the_approved_moves():
    proposals = tune.propose(_votes(), [])
    assert proposals, "five 👎 small moves vs four 👍 big ones should give a rule"
    p = proposals[0]
    assert p["check"] == "L008" and p["fix"] == "move"
    cut = p["when"].get("move_in", p["when"].get("past_border_in"))["max"]
    assert 0.06 <= cut < 0.4
    after = tune.replay([p], _votes())
    assert after.get("removed_down") == 5 and not after.get("removed_up")


def test_no_proposal_from_too_few_or_mixed_votes():
    assert tune.propose(_votes()[:2], []) == []
    mixed = [_vote(i, "up" if i % 2 else "down", 0.1) for i in range(8)]
    assert tune.propose(mixed, []) == []
    assert tune.questions(mixed) and "L008 move" in tune.questions(mixed)[0]


def test_report_and_apply(tmp_path, monkeypatch):
    fb = tmp_path / "fb"
    _write(fb, _votes())
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "tuning.yaml").write_text("# Tuning gates (test copy)\ngates: []\n", encoding="utf-8")
    monkeypatch.setattr(rules, "RULES_DIR", rules_dir)
    rules.load.cache_clear()
    try:
        out = tmp_path / "report.md"
        assert tune.main(SimpleNamespace(votes=str(fb), apply=None, json=False, out=str(out))) == 0
        text = out.read_text(encoding="utf-8")
        assert "P1:" in text and "L008 move" in text and "Not worth it: 5" in text
        assert tune.main(SimpleNamespace(votes=str(fb), apply="P1", json=False, out=None)) == 0
        [gate] = tuning.gates()
        assert gate["id"] == "T001" and gate["action"] == "skip" and gate["check"] == "L008"
        assert tuning.gate_for(_vote(0, "down", 0.03)["changes"][0]) is not None
        assert tuning.gate_for(_vote(0, "up", 0.9)["changes"][0]) is None
        assert (rules_dir / "tuning.yaml").read_text(encoding="utf-8").startswith("# Tuning gates (test copy)")
    finally:
        rules.load.cache_clear()
