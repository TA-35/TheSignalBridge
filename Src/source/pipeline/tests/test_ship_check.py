"""Ship check tests: CLAUDE.md's rule, and when its verdict counts."""
from __future__ import annotations

import csv
import json

from Src.source.pipeline import ship_check as sc


def row(model, recall, nli, wins=None, losses=None):
    r = {"dataset": "all", "model": model, "entity_recall": str(recall), "nli_entailment": str(nli),
         "judge_wins": "", "judge_losses": "", "judge_ties": "0", "judge_no_decision": "0"}
    if wins is not None:
        r.update(judge_wins=str(wins), judge_losses=str(losses))
    return r


BASE = row("baseline", 0.80, 0.70)
READY = {"judge_trusted": True, "gold_lock": "locked", "preview": False}


def test_ships_the_finetuned_model_when_every_rule_passes():
    assert sc.decide(BASE, row("run2", 0.95, 0.75, 40, 10), **READY)["verdict"] == "SHIP run2"


def test_two_points_lower_is_allowed_and_more_is_not():
    assert sc.decide(BASE, row("run2", 0.78, 0.68, 40, 10), **READY)["verdict"] == "SHIP run2"
    assert sc.decide(BASE, row("run2", 0.7799, 0.70, 40, 10), **READY)["verdict"] == "SHIP baseline"
    assert sc.decide(BASE, row("run2", 0.80, 0.6799, 40, 10), **READY)["verdict"] == "SHIP baseline"


def test_not_beating_the_baseline_with_the_judge_ships_the_baseline():
    assert sc.decide(BASE, row("run2", 0.95, 0.75, 10, 10), **READY)["verdict"] == "SHIP baseline"
    assert sc.decide(BASE, row("run2", 0.95, 0.75), **READY)["verdict"] == "SHIP baseline"   # never judged


def test_undecided_until_the_judge_is_validated_and_the_gold_locked():
    ft = row("run2", 0.95, 0.75, 40, 10)
    for trusted, lock in ((None, "locked"), (False, "locked"), (True, "not locked"), (True, "CHANGED since lock: x")):
        assert sc.decide(BASE, ft, judge_trusted=trusted, gold_lock=lock, preview=False)["verdict"] == "UNDECIDED"
    assert sc.decide(BASE, ft, judge_trusted=None, gold_lock="not locked", preview=True)["verdict"] \
        == "PREVIEW: SHIP run2"


def test_exit_status_and_decision_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sc, "gold_lock_status", lambda: "locked")
    (tmp_path / "eval").mkdir()

    def results(ft):
        with (tmp_path / "eval/results.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(BASE))
            w.writeheader()
            w.writerows([BASE, ft])

    results(row("run2", 0.95, 0.75, 40, 10))
    assert sc.main(["--finetuned", "run2"]) == 2                       # judge not validated yet
    (tmp_path / "eval/judge_validation.json").write_text(json.dumps({"trust_judge": True}))
    assert sc.main(["--finetuned", "run2"]) == 0
    assert json.loads((tmp_path / "eval/ship_decision.json").read_text())["verdict"] == "SHIP run2"
    results(row("run2", 0.70, 0.75, 40, 10))                           # recall 10 points down
    assert sc.main(["--finetuned", "run2"]) == 1
    assert json.loads((tmp_path / "eval/ship_decision.json").read_text())["verdict"] == "SHIP baseline"
