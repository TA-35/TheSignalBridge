"""Tests for gold_lock.py on a small synthetic gold set - plus, once
data/gold/LOCK.json exists, a check that the real gold still matches it."""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("gold_lock", HERE.parent / "gold_lock.py")
gl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gl)


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture
def root(tmp_path, monkeypatch):
    """Two messages per dataset, every draft checked: ready to lock."""
    monkeypatch.setattr(gl, "PER_DATASET", 2)
    monkeypatch.setattr(gl, "ROOT", tmp_path)
    for ds in gl.DATASETS:
        gold_rel, draft_rel = gl.gold_files(ds)
        gold = [{"id": f"{ds}_{i}", "dataset": ds, "source": f"message {i}"} for i in range(2)]
        _write(tmp_path / gold_rel, gold)
        _write(tmp_path / draft_rel, [dict(g, rewrite=f"Rewrite {i}.", notes=["Made the ask direct."],
                                           checked_by="Amulya") for i, g in enumerate(gold)])
    return tmp_path


def _edit_drafts(root, ds, change):
    path = root / gl.gold_files(ds)[1]
    _write(path, change(_read(path)))


# --------------------------------------------------------------------------
# What stops a lock
# --------------------------------------------------------------------------

def test_a_complete_checked_gold_set_is_ready(root):
    assert gl.problems(root) == {ds: [] for ds in gl.DATASETS}


@pytest.mark.parametrize("change, expected", [
    (lambda rows: [{k: v for k, v in r.items() if k != "checked_by"} for r in rows],
     "2 drafts not checked"),
    (lambda rows: [dict(r, checked_by="  ") for r in rows], "2 drafts not checked"),
    (lambda rows: [dict(rows[0], rewrite=""), rows[1]], "1 drafts without a rewrite and 1-3 notes"),
    (lambda rows: [dict(rows[0], notes=[]), rows[1]], "1 drafts without a rewrite and 1-3 notes"),
    (lambda rows: [dict(rows[0], source="edited"), rows[1]], "1 drafts have different source text"),
    (lambda rows: [rows[0], dict(rows[1], id="stanford_99")], "draft ids differ from gold ids"),
    (lambda rows: [rows[0], dict(rows[1], id=rows[0]["id"])], "drafts ids are missing or repeated"),
    (lambda rows: rows[:1], "1 drafts, need 2"),
])
def test_each_problem_blocks_only_its_dataset(root, change, expected):
    _edit_drafts(root, "stanford", change)
    found = gl.problems(root)
    assert any(expected in issue for issue in found["stanford"]), found["stanford"]
    assert found["enron"] == [] and found["circa"] == []


def test_a_missing_drafts_file_is_reported(root):
    (root / gl.gold_files("circa")[1]).unlink()
    assert gl.problems(root)["circa"] == ["no data/gold_drafts/circa_gold_draft.jsonl"]


def test_a_corrupt_line_is_reported_not_skipped(root):
    path = root / gl.gold_files("enron")[0]
    path.write_text(path.read_text() + "{cut off\n")
    assert any("unreadable" in issue for issue in gl.problems(root)["enron"])


# --------------------------------------------------------------------------
# Lock and verify
# --------------------------------------------------------------------------

def test_lock_refuses_until_ready_and_writes_nothing(root):
    _edit_drafts(root, "stanford", lambda rows: [dict(r, checked_by="") for r in rows])
    with pytest.raises(SystemExit, match="stanford: 2 drafts not checked"):
        gl.lock(root)
    assert not (root / gl.LOCK_FILE).exists()


def test_lock_records_every_gold_file_and_verify_passes(root):
    record = gl.lock(root)
    assert set(record["files"]) == {str(rel) for ds in gl.DATASETS for rel in gl.gold_files(ds)}
    assert record["files"]["data/gold/enron_gold.jsonl"] == gl._sha256(root / "data/gold/enron_gold.jsonl")
    assert gl.changed_since_lock(root) == []


def test_verify_names_a_file_edited_after_the_lock_until_it_is_relocked(root):
    gl.lock(root)
    _edit_drafts(root, "enron", lambda rows: [dict(rows[0], rewrite="Changed after the lock."), rows[1]])
    assert gl.changed_since_lock(root) == ["data/gold_drafts/enron_gold_draft.jsonl"]
    gl.lock(root)                                      # a deliberate re-lock
    assert gl.changed_since_lock(root) == []


def test_not_locked_is_none_not_a_pass(root):
    assert gl.changed_since_lock(root) is None


def test_cli_exit_codes(root, capsys):
    assert gl.main(["verify"]) == 2                    # not locked yet
    assert gl.main(["lock"]) == 0
    assert gl.main(["verify"]) == 0
    _edit_drafts(root, "circa", lambda rows: rows[:1])
    assert gl.main(["verify"]) == 1
    assert gl.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "CHANGED since locking: data/gold_drafts/circa_gold_draft.jsonl" in out
    assert "message 0" not in out                      # counts and ids only, never message text


# --------------------------------------------------------------------------
# The real gold set
# --------------------------------------------------------------------------

def test_the_real_gold_set_matches_its_lock():
    """Skipped until the team locks gold. From then on, editing a gold file
    fails here until someone re-locks it on purpose."""
    changed = gl.changed_since_lock(gl.ROOT)
    if changed is None:
        pytest.skip("gold is not locked yet (data/gold/LOCK.json does not exist)")
    assert changed == [], f"gold changed since it was locked: {changed} - revert, or re-lock on purpose"
