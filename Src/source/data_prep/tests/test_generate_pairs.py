"""Tests for the teacher generation script. The API is always faked."""
import json
import urllib.request
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from Src.source.data_prep import generate_pairs as gp
from Src.source.pipeline import compose_prompt as cp

HERE = Path(__file__).resolve().parent
fp = SourceFileLoader("filter_pairs", str(HERE.parent / "filter_pairs.py")).load_module()

SIGNALS = [{"model": "tone", "label": "casual", "confidence": 0.9},
           {"model": "politeness", "label": "high", "confidence": 0.555},
           {"model": "circa", "label": "direct", "confidence": 0.6}]
MEANING = {"ask": "Check the deck", "deadline": "", "urgency": "low", "tone": "casual", "implied": ""}
GOOD = json.dumps({"meaning": MEANING, "rewrite": "Could you check the deck?", "notes": ["Made the ask direct."]})


def _source(tmp_path, ids, folder="source", name="enron_source.jsonl", signals=SIGNALS):
    path = tmp_path / "data" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"id": i, "dataset": "enron", "source": f"can u check the deck {i}",
                                        "signals": signals}) + "\n" for i in ids))


def _written(tmp_path, rel="data/generated/enron_gen.jsonl"):
    return [json.loads(l) for l in (tmp_path / rel).read_text().splitlines()]


def test_usable_answer_is_written_for_the_filter(tmp_path):
    _source(tmp_path, ["a"])
    counts = gp.run("enron", root=tmp_path, ask=lambda r: GOOD)
    (row,) = _written(tmp_path)
    assert counts == {"written": 1, "raw": 0, "failed": 0, "skipped": 0}
    assert list(row) == ["id", "dataset", "source", "signals", "meaning", "rewrite", "notes",
                         "model", "prompt_version"]
    assert row["prompt_version"] == cp.fingerprint() and row["model"] == gp.MODEL
    assert row["meaning"] == MEANING and row["rewrite"] == "Could you check the deck?"


def test_unusable_answer_is_kept_raw_so_the_filter_counts_it(tmp_path):
    _source(tmp_path, ["a"])
    counts = gp.run("enron", root=tmp_path, ask=lambda r: "Sorry, I can't help with that.")
    (row,) = _written(tmp_path)
    assert counts["raw"] == 1 and "rewrite" not in row and row["raw"].startswith("Sorry")
    unpacked, problem = fp.unpack(row)
    assert problem or fp.check_json(unpacked)      # rejected by json_valid


def test_no_answer_is_not_written_and_a_rerun_picks_it_up(tmp_path):
    _source(tmp_path, ["a", "b", "c"])

    def flaky(record):
        if record["id"] == "b":
            raise gp.TeacherError("no answer after 4 tries (HTTP 504)")
        return GOOD

    assert gp.run("enron", root=tmp_path, ask=flaky, workers=1)["failed"] == 1
    assert [r["id"] for r in _written(tmp_path)] == ["a", "c"]

    asked = []
    gp.run("enron", root=tmp_path, ask=lambda r: asked.append(r["id"]) or GOOD)
    assert asked == ["b"]
    assert sorted(r["id"] for r in _written(tmp_path)) == ["a", "b", "c"]


def test_limit_counts_new_records_only(tmp_path):
    _source(tmp_path, ["a", "b", "c", "d"])
    gp.run("enron", root=tmp_path, ask=lambda r: GOOD, limit=2, workers=1)
    gp.run("enron", root=tmp_path, ask=lambda r: GOOD, limit=1, workers=1)
    assert [r["id"] for r in _written(tmp_path)] == ["a", "b", "c"]


def test_gold_drafts_never_go_to_generated(tmp_path):
    _source(tmp_path, ["g1"], folder="gold", name="enron_gold.jsonl")
    gp.run("enron", gold=True, root=tmp_path, ask=lambda r: GOOD)
    assert [r["id"] for r in _written(tmp_path, "data/gold_drafts/enron_gold_draft.jsonl")] == ["g1"]
    assert not (tmp_path / "data" / "generated").exists()


def test_records_without_signals_are_skipped(tmp_path):
    _source(tmp_path, ["a"], signals=None)
    asked = []
    counts = gp.run("enron", root=tmp_path, ask=lambda r: asked.append(r) or GOOD)
    assert asked == [] and counts["skipped"] == 1


def test_missing_input_file_is_skipped(tmp_path):
    assert gp.run("circa", root=tmp_path, ask=lambda r: GOOD)["written"] == 0


def test_bad_key_stops_the_run(tmp_path):
    _source(tmp_path, ["a", "b", "c"])
    asked = []

    def unauthorised(record):
        asked.append(record["id"])
        raise gp.TeacherConfigError("HTTP 401")

    with pytest.raises(SystemExit, match="HTTP 401"):
        gp.run("enron", root=tmp_path, ask=unauthorised, workers=1)
    assert asked == ["a"]


def test_request_follows_the_teacher_spec(monkeypatch):
    sent = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": GOOD}}]}).encode()

    def fake_urlopen(request, timeout):
        sent.update(body=json.loads(request.data), auth=request.get_header("Authorization"))
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    record = {"id": "a", "source": "can u check the deck", "signals": SIGNALS}
    assert gp.ask_teacher(record, "nvapi-test") == GOOD
    assert sent["auth"] == "Bearer nvapi-test"
    assert sent["body"]["model"] == "deepseek-ai/deepseek-v4.1-flash"
    assert sent["body"]["temperature"] == 0.3 and sent["body"]["max_tokens"] == 4000
    assert sent["body"]["messages"] == cp.build_messages("can u check the deck", SIGNALS, few_shot=True)


def test_api_key_comes_from_env_or_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OTHER=1\nNVIDIA_API_KEY='nvapi-from-file'\n")
    monkeypatch.setattr(gp, "ENV_FILES", (tmp_path / "missing.env", env))
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert gp.api_key() == "nvapi-from-file"
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-exported")
    assert gp.api_key() == "nvapi-exported"
