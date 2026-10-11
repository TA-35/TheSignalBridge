"""Rating sheet tests: blind, one order per rater, and collected back into the
file validate_judge reads."""
from __future__ import annotations

import csv
import json

import pytest

from Src.source.pipeline import compose_prompt as cp
from Src.source.pipeline import rating_sheets as rs


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def root(tmp_path):
    for ds in ("enron", "stanford", "circa"):
        source = "Q: Are you coming on Friday?\nReply: Maybe." if ds == "circa" else "Could you send it?"
        write(tmp_path / f"data/gold/{ds}_gold.jsonl", [{"id": f"{ds}_{i}", "source": source} for i in range(8)])
        for name, few_shot in (("baseline", True), ("run2", False)):
            write(tmp_path / f"eval/{ds}/{name}.jsonl",
                  [{"id": f"{ds}_{i}", "prompt": cp.fingerprint(), "few_shot": few_shot,
                    "rewrite": f"Rewrite {i}{'x' if few_shot else 'y'}", "notes": ["n"],
                    "meaning": {"ask": "a"}} for i in range(8)])
    return tmp_path


def make(root):
    return rs.make("baseline", "run2", ["ann", "bo"], 2, 7, root / "eval", root / "data/gold")


def sheet(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_sheets_are_blind_and_each_rater_gets_their_own_order(root):
    out = make(root)
    key = json.loads((out / "key.json").read_text())["items"]
    assert len(key) == 3 * 2 * 2                              # 2 messages per dataset x 2 models
    assert sorted(k["model"] for k in key.values()).count("finetuned") == 6
    ann, bo = sheet(out / "sheet_ann.csv"), sheet(out / "sheet_bo.csv")
    assert list(ann[0]) == rs.SHEET_COLUMNS and "model" not in ann[0]
    for name in ("ann", "bo"):
        text = (out / f"sheet_{name}.csv").read_text()
        assert "run2" not in text and "baseline" not in text and "finetuned" not in text
    assert {r["item"] for r in ann} == {r["item"] for r in bo} == set(key)
    assert [r["item"] for r in ann] != [r["item"] for r in bo]
    circa = [r for r in ann if key[r["item"]]["dataset"] == "circa"]
    assert circa and all(r["question"] == "Are you coming on Friday?" and r["message"] == "Maybe." for r in circa)
    assert "meaning_kept: 2 = same meaning" in (out / "README.md").read_text()     # the judge's own rubric


def test_collect_turns_the_filled_sheets_into_human_scores(root):
    out = make(root)
    key = json.loads((out / "key.json").read_text())["items"]
    for name in ("ann", "bo"):
        rows = sheet(out / f"sheet_{name}.csv")
        for n, r in enumerate(rows):
            r.update(meaning_kept="2", clarity="1", warmth="2", notes_accurate="" if n == 0 else "0")
        with (out / f"sheet_{name}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rs.SHEET_COLUMNS)
            w.writeheader()
            w.writerows(rows)
    rs.collect(root / "eval")
    human = sheet(root / "eval/human_scores.csv")
    assert list(human[0]) == rs.HUMAN_COLUMNS
    assert len(human) == 2 * (len(key) - 1)                    # each rater's unfinished row is left out
    assert {h["rater"] for h in human} == {"ann", "bo"} and {h["model"] for h in human} == {"baseline", "finetuned"}
    pairs = {(k["id"], k["model"]) for k in key.values()}
    assert all((h["id"], h["model"]) in pairs for h in human)
