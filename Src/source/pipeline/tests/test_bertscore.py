"""BERTScore wrapper tests, with the scorer faked: no model download."""
import json

from Src.source.pipeline import bertscore as bs


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_scores_only_the_ids_every_model_answered(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(bs, "f1_scores", lambda cands, refs, model_type=None: seen.append(list(cands)) or [0.5] * len(cands))
    write(tmp_path / "gold.jsonl", [{"id": i, "rewrite": "gold"} for i in "abc"])
    write(tmp_path / "base.jsonl", [{"id": i, "rewrite": "x"} for i in "abc"])
    write(tmp_path / "ft.jsonl", [{"id": "a", "rewrite": "y"}, {"id": "b", "error": "not JSON"}])
    res = bs.run(tmp_path / "gold.jsonl", [("baseline", tmp_path / "base.jsonl"), ("run2", tmp_path / "ft.jsonl")],
                 tmp_path / "out.json")
    assert res["scored_ids"] == 1 and seen == [["x"], ["y"]]
    assert res["per_model"]["run2"] == {"n": 1, "missing": 2, "mean_f1": 0.5}
    assert res["per_model"]["baseline"]["missing"] == 0
