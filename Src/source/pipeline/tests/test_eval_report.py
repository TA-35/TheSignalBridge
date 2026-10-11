"""Eval report tests: build() on a temporary eval/ folder with the metrics and
BERTScore faked, worst-20 ranking, the rubric scoring step and results.csv."""
from __future__ import annotations

import csv
import json

import pytest

from Src.source.pipeline import compose_prompt as cp
from Src.source.pipeline import eval_report as er
from Src.source.pipeline import judge as J

DATASETS = ("enron", "circa")


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def pred(rid, rewrite="rw", few_shot=False, **extra):
    return {"id": rid, "source": "s", "prompt": cp.fingerprint(), "few_shot": few_shot, "rewrite": rewrite,
            "notes": ["n"], "meaning": {"ask": ""}, **extra}


def fake_metrics(gold, preds):
    """One row per gold id; a "bad" rewrite is ungrounded."""
    rows = []
    for g in gold:
        p = preds.get(g["id"], {"error": "no prediction"})
        ok = "error" not in p
        good = ok and p["rewrite"] != "bad"
        rows.append({"id": g["id"], "dataset": g["dataset"], "usable": ok, "entities": 1, "kept": int(good),
                     "grounded": good, "added": False, "nli": "entailment" if ok else None, "length_ratio": 1.0,
                     "is_circa": False, "politeness": ["medium", "medium"]})
    return rows


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for ds in DATASETS:
        write(tmp_path / f"data/gold/{ds}_gold.jsonl", [{"id": f"{ds}_{i}", "dataset": ds, "source": "s"} for i in range(3)])
        write(tmp_path / f"eval/{ds}/baseline.jsonl", [pred(f"{ds}_{i}", few_shot=True) for i in range(3)])
        write(tmp_path / f"eval/{ds}/run2.jsonl", [pred(f"{ds}_{i}", "bad" if i == 0 else "rw") for i in range(3)])
    return tmp_path


def build(root, f1=None):
    return er.build("baseline", ["run2"], DATASETS, root / "eval", root / "data/gold", root / "data/gold_drafts",
                    metrics=fake_metrics, f1_fn=f1 or (lambda cands, refs: [0.5] * len(cands)))


def test_predictions_made_with_another_prompt_are_refused(root):
    write(root / "eval/enron/run2.jsonl", [dict(pred("enron_0"), prompt="0123456789ab")])
    with pytest.raises(SystemExit, match="prompt"):
        build(root)


def test_a_zero_shot_baseline_or_a_few_shot_finetuned_model_is_refused(root):
    write(root / "eval/enron/baseline.jsonl", [pred(f"enron_{i}", few_shot=False) for i in range(3)])
    with pytest.raises(SystemExit, match="few_shot"):
        build(root)
    write(root / "eval/enron/baseline.jsonl", [pred(f"enron_{i}", few_shot=True) for i in range(3)])
    write(root / "eval/enron/run2.jsonl", [pred(f"enron_{i}", few_shot=True) for i in range(3)])
    with pytest.raises(SystemExit, match="few_shot"):
        build(root)


def test_metrics_per_dataset_and_pooled(root):
    rows, per_message, preds, _ = build(root)
    by = {(r["dataset"], r["model"]): r for r in rows}
    assert by[("enron", "run2")]["grounded"] == pytest.approx(2 / 3)
    assert by[("all", "run2")]["grounded"] == pytest.approx(4 / 6) and by[("all", "run2")]["n"] == 6
    assert by[("all", "baseline")]["grounded"] == 1
    assert len(per_message["run2"]) == 6 and set(preds["run2"]) == {f"{d}_{i}" for d in DATASETS for i in range(3)}


def test_bertscore_needs_every_gold_rewrite_checked_and_uses_shared_ids(root):
    write(root / "data/gold_drafts/enron_gold_draft.jsonl",
          [{"id": f"enron_{i}", "rewrite": "gold", "checked_by": "Amulya"} for i in range(3)])
    write(root / "data/gold_drafts/circa_gold_draft.jsonl",
          [{"id": f"circa_{i}", "rewrite": "gold", "checked_by": "" if i == 0 else "x"} for i in range(3)])
    write(root / "eval/enron/baseline.jsonl", [pred("enron_0", few_shot=True), pred("enron_1", few_shot=True),
                                              pred("enron_2", few_shot=True, error="timeout")])
    calls = []
    rows, _, _, meta = build(root, f1=lambda cands, refs: calls.append(len(cands)) or [0.5] * len(cands))
    assert calls == [2, 2]                      # Enron only, on the 2 ids both models answered
    assert meta["bertscore"]["circa"].startswith("skipped")
    by = {(r["dataset"], r["model"]): r for r in rows}
    assert by[("enron", "run2")]["bertscore_f1"] == 0.5 and by[("circa", "run2")]["bertscore_f1"] is None


def test_judge_counts_pool_over_datasets(root):
    for ds, (wins, losses) in {"enron": (2, 1), "circa": (1, 0)}.items():
        out = root / f"eval/{ds}/baseline_vs_run2"
        out.mkdir(parents=True)
        (out / "judge_summary.json").write_text(json.dumps(
            {"wins_run2": wins, "wins_baseline": losses, "ties": 0, "no_decision": 3 - wins - losses,
             "rubric": J.RUBRIC_ID}))
        write(out / "judge_pairs.jsonl", [])
    rows, *_ = build(root)
    by = {(r["dataset"], r["model"]): r for r in rows}
    ft = by[("all", "run2")]
    assert (ft["judge_wins"], ft["judge_losses"], ft["judge_no_decision"]) == (3, 1, 2)
    assert ft["judge_win_rate"] == 0.75 and by[("enron", "run2")]["judge_win_rate"] == pytest.approx(2 / 3)
    assert by[("all", "baseline")].get("judge_win_rate") is None


def test_worst20_puts_failed_answers_first_then_ungrounded_then_judge_losses():
    pytest.importorskip("spacy")
    try:
        er.fp.nlp()
    except OSError:
        pytest.skip("en_core_web_sm not installed")
    gold = {i: {"id": i, "source": "Please send the report to Dana."} for i in "abcd"}
    preds = {i: {"rewrite": "Please send the report to Dana.", "notes": ["n"]} for i in "cd"}
    preds["b"] = {"rewrite": "Please send the report.", "notes": ["n"]}
    base = {"dataset": "enron", "model": "run2", "f1": None, "rubric": None, "verdict": None}
    lost = {"winner": "baseline", "order_ab": {"reason": "x"}, "order_ba": {"reason": "y"}}
    rows = [dict(base, id="d", usable=True, grounded=True, verdict=lost),
            dict(base, id="c", usable=True, grounded=True),
            dict(base, id="b", usable=True, grounded=False),
            dict(base, id="a", usable=False, grounded=False, error="reply isn't JSON")]
    md = er.worst20("run2", rows, gold, preds)
    assert [line.split()[2] for line in md.splitlines() if line.startswith("## ")] == ["a", "b", "d"]
    assert "dropped ['Dana']" in md and "judge preferred baseline" in md


def test_score_skips_scored_ids_and_records_judge_errors(root, monkeypatch):
    from Src.source.pipeline import judge

    calls = []

    def fake(source, signals, output):
        calls.append(output["rewrite"])
        if output["rewrite"] == "bad":
            raise judge.JudgeError("no verdict")
        return judge.Scores(2, 1, 2, 1, model="m")

    monkeypatch.setattr(judge, "score_output", fake)
    scored = {"meaning_kept": 2, "clarity": 2, "warmth": 2, "notes_accurate": 2, "total": 8}
    write(root / "eval/enron/run2_scores.jsonl", [{"id": "enron_1", **scored, "rubric": J.RUBRIC_ID},
                                                  {"id": "enron_2", **scored, "rubric": "oldrubric000"}])
    er.score(["run2"], ("enron",), root / "eval", root / "data/gold", "baseline", workers=1)
    assert sorted(calls) == ["bad", "rw"]     # enron_1 was already scored; enron_2 only with an old rubric
    scored = er.read_jsonl(root / "eval/enron/run2_scores.jsonl")
    assert {r["id"]: "error" in r for r in scored} == {"enron_1": False, "enron_0": True, "enron_2": False}
    assert er.rubric(root / "eval", "enron", "run2")["enron_2"]["total"] == 6
    calls.clear()
    er.score(["run2"], ("enron",), root / "eval", root / "data/gold", "baseline", workers=1)
    assert calls == ["bad"]                             # only the failed one is tried again


def test_results_csv_keeps_the_column_order_and_rounds(tmp_path):
    er.write_csv([{"dataset": "all", "model": "run2", "entity_recall": 0.912345678, "extra": 1}], tmp_path / "r.csv")
    with (tmp_path / "r.csv").open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert reader.fieldnames == er.COLUMNS and row["entity_recall"] == "0.9123"


def test_gold_lock_status(tmp_path):
    assert er.gold_lock_status(tmp_path) == "not locked"
    gold = tmp_path / "data/gold/enron_gold.jsonl"
    write(gold, [{"id": 1}])
    (tmp_path / "data/gold/LOCK.json").write_text(json.dumps({"files": {"data/gold/enron_gold.jsonl": er.sha256(gold)}}))
    assert er.gold_lock_status(tmp_path) == "locked"
    write(gold, [{"id": 2}])
    assert er.gold_lock_status(tmp_path).startswith("CHANGED")


def test_verdicts_from_another_judge_rubric_are_refused(root):
    out = root / "eval/enron/baseline_vs_run2"
    out.mkdir(parents=True)
    (out / "judge_summary.json").write_text(json.dumps({"wins_run2": 1, "wins_baseline": 0, "rubric": "oldrubric000"}))
    write(out / "judge_pairs.jsonl", [])
    with pytest.raises(SystemExit, match="rubric"):
        build(root)
