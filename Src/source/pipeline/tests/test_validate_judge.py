"""validate_judge with one file per dataset; the scorer is faked."""
import json

import pytest

pytest.importorskip("scipy")

from Src.source.pipeline import judge as J  # noqa: E402
from Src.source.pipeline import validate_judge as VJ  # noqa: E402


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_rated_outputs_from_every_dataset_are_correlated_together(tmp_path, monkeypatch):
    human = ["id,dataset,model,rater,meaning_kept,clarity,warmth,notes_accurate,comment"]
    files = {}
    for ds in ("enron", "circa"):
        write(tmp_path / f"{ds}_gold.jsonl", [{"id": f"{ds}_{i}", "source": "s"} for i in range(3)])
        for model in ("baseline", "finetuned"):
            write(tmp_path / f"{ds}_{model}.jsonl", [{"id": f"{ds}_{i}", "rewrite": f"{model} {i}"} for i in range(3)])
        files.setdefault("source", []).append(str(tmp_path / f"{ds}_gold.jsonl"))
        for model in ("baseline", "finetuned"):
            files.setdefault(model, []).append(str(tmp_path / f"{ds}_{model}.jsonl"))
            human += [f"{ds}_{i},{ds},{model},ann,{i % 3},{i % 3},2,1," for i in range(3)]
    (tmp_path / "human.csv").write_text("\n".join(human) + "\n", encoding="utf-8")
    # the judge agrees with the humans exactly
    monkeypatch.setattr(VJ, "score_output", lambda source, signals, out: J.Scores(
        int(out["rewrite"][-1]) % 3, int(out["rewrite"][-1]) % 3, 2, 1, model="m"))
    VJ.run(str(tmp_path / "human.csv"), files["source"], files["baseline"], files["finetuned"],
           str(tmp_path / "out.json"))
    result = json.loads((tmp_path / "out.json").read_text())
    assert result["n"] == 12 and result["total"]["rho"] == 1.0 and result["trust_judge"] is True
