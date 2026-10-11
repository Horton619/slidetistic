import json

import pytest

from engine import cli
from engine.core import Status
from engine.core.runner import RunConfig, output_path_for, repair, scan
from tests.fixtures.builders import make_deck, picture, text_box


def by_check(result, check_id):
    return [f for f in result.findings if f.check_id == check_id]


def test_scan_finds_and_changes_nothing(tmp_path, checks_with_dummies):
    src = make_deck(tmp_path, text_box("off", x=-0.56), picture(x=-2))
    before = src.read_bytes()
    result = scan(src, checks_with_dummies, RunConfig())
    assert [f.status for f in by_check(result, "X999")] == [Status.RED]
    assert src.read_bytes() == before


def test_repair_verifies_fix_by_rescan(tmp_path, checks_with_dummies):
    src = make_deck(tmp_path, text_box("off", x=-0.56), picture(x=-2))
    result = repair(src, checks_with_dummies, RunConfig())
    assert [f.status for f in by_check(result, "X999")] == [Status.GREEN_FIXED]
    assert len(result.changes) == 1 and result.changes[0].prop == "left"
    assert result.output_path.name == "deck - mended.pptx"


def test_fix_off_leaves_problem_red(tmp_path, checks_with_dummies):
    src = make_deck(tmp_path, text_box("off", x=-0.56))
    result = repair(src, checks_with_dummies, RunConfig(fixes=set()))
    assert [f.status for f in by_check(result, "X999")] == [Status.RED]
    assert result.changes == []


def test_crashing_check_is_reported_and_others_still_run(tmp_path, checks_with_dummies):
    src = make_deck(tmp_path, text_box("off", x=-0.56))
    result = scan(src, checks_with_dummies, RunConfig())
    assert [f.status for f in by_check(result, "X998")] == [Status.TOOL_ERROR]
    assert by_check(result, "X999")


def test_output_never_overwrites(tmp_path):
    src = make_deck(tmp_path, text_box())
    (tmp_path / "deck - mended.pptx").write_bytes(b"x")
    assert output_path_for(src).name == "deck - mended (2).pptx"


def test_refuses_to_write_over_input(tmp_path, checks_with_dummies):
    src = make_deck(tmp_path, text_box())
    with pytest.raises(ValueError):
        repair(src, checks_with_dummies, RunConfig(), out_path=src)


def test_cli_list_checks_json(capsys):
    assert cli.main(["list-checks", "--json"]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), list)


def test_cli_rejects_non_pptx(tmp_path, capsys):
    odp = tmp_path / "talk.odp"
    odp.write_bytes(b"")
    assert cli.main(["scan", str(odp), "--json"]) == 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["type"] == "error"


def test_cli_rejects_a_damaged_keynote_file_without_launching_keynote(tmp_path, capsys, monkeypatch):
    import subprocess
    from engine import keynote
    monkeypatch.setattr(keynote, "keynote_app", lambda: ("com.apple.Keynote", "Keynote Creator Studio"))
    monkeypatch.setattr(keynote, "unavailable_reason", lambda: None)
    real_run = subprocess.run

    def no_osascript(cmd, *a, **kw):
        assert cmd[0] != "osascript", "Keynote must not be launched for a damaged file"
        return real_run(cmd, *a, **kw)
    monkeypatch.setattr(keynote.subprocess, "run", no_osascript)
    key = tmp_path / "talk.key"
    key.write_bytes(b"")
    assert cli.main(["scan", str(key), "--json"]) == 2
    err = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert err["type"] == "error" and "isn't a valid Keynote file" in err["message"]


def test_cli_explains_folder_named_pptx(tmp_path, capsys):
    # Dropbox 2026-10-09: "Friday Morning Opening Session.pptx" was a folder of slide JPEGs.
    folder = tmp_path / "Opening Session.pptx"
    folder.mkdir()
    (folder / "1.jpg").write_bytes(b"x")
    assert cli.main(["scan", str(folder), "--json"]) == 2
    assert "folder of slide images" in json.loads(capsys.readouterr().out)["message"]


def test_cli_explains_damaged_file(tmp_path, capsys):
    bad = tmp_path / "broken.pptx"
    bad.write_bytes(b"not a zip")
    assert cli.main(["scan", str(bad), "--json"]) == 2
    assert "isn't a valid PowerPoint file" in json.loads(capsys.readouterr().out)["message"]


def test_introduced_findings_keep_their_severity_and_name_the_cause():
    # David 2026-10-10: an orphan caused by a font fix is "needs a look", not an emergency.
    from engine.core import Change, Finding
    from engine.core.runner import _reconcile
    after = [Finding("L009", Status.YELLOW, "'struggles?' alone", slide=19, shape_id=3, subject="para0"),
             Finding("L008", Status.RED, "off the bottom", slide=29, shape_id=2, subject="off-slide")]
    changes = [Change("F001", None, None, None, "font name", "Roboto Slab Bold", "Roboto Slab", part="/ppt/slides/slide19.xml")]
    out = {f.check_id: f for f in _reconcile([], after, {}, changes)}
    assert out["L009"].status == Status.YELLOW and out["L009"].evidence["introduced_by"] == "F001"
    assert out["L008"].status == Status.RED
