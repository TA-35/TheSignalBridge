"""Eval judge logic tests. _call is faked, so no API key or network is needed."""
import json

import pytest

from Src.source.pipeline import judge as J
from Src.source.pipeline import run_judge as RJ

def _fake_call(seq):
    seq = list(seq)
    def fake(system, user, _retried=False):
        return seq.pop(0)
    return fake

def test_system_winner_mapping():
    assert J._system_winner("A", True) == "a"
    assert J._system_winner("B", True) == "b"
    assert J._system_winner("A", False) == "b"
    assert J._system_winner("B", False) == "a"
    assert J._system_winner("tie", True) == "tie"

def test_judge_pair_agree(monkeypatch):
    # A-first picks A (=a); B-first picks B (=a): both say a
    monkeypatch.setattr(J, "_call", _fake_call([
        {"winner": "A", "reason": "x"}, {"winner": "B", "reason": "y"}]))
    r = J.judge_pair("s", None, {"rewrite": "a"}, {"rewrite": "b"})
    assert r.winner == "a" and r.agree is True


def test_judge_pair_no_decision(monkeypatch):
    # both orderings pick position A -> different systems -> disagree
    monkeypatch.setattr(J, "_call", _fake_call([
        {"winner": "A", "reason": "x"}, {"winner": "A", "reason": "y"}]))
    r = J.judge_pair("s", None, {"rewrite": "a"}, {"rewrite": "b"})
    assert r.winner == "no_decision" and r.agree is False


def test_judge_pair_tie(monkeypatch):
    monkeypatch.setattr(J, "_call", _fake_call([
        {"winner": "tie", "reason": "x"}, {"winner": "tie", "reason": "y"}]))
    r = J.judge_pair("s", None, {"rewrite": "a"}, {"rewrite": "b"})
    assert r.winner == "tie" and r.agree is True


def test_score_output_clamps(monkeypatch):
    monkeypatch.setattr(J, "_call", _fake_call([
        {"meaning_kept": 2, "clarity": 1, "warmth": 3, "notes_accurate": 0}]))
    s = J.score_output("s", None, {"rewrite": "a", "notes": [], "meaning": {}})
    assert (s.meaning_kept, s.clarity, s.warmth, s.notes_accurate) == (2, 1, 2, 0)
    assert s.total == 5


def test_run_judge_summary(monkeypatch, tmp_path):
    ids = ["1", "2", "3"]
    (tmp_path / "s.jsonl").write_text(
        "\n".join(json.dumps({"id": i, "source": "s", "signals": None}) for i in ids),
        encoding="utf-8")
    (tmp_path / "a.jsonl").write_text(
        "\n".join(json.dumps({"id": i, "rewrite": "x"}) for i in ids), encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(
        "\n".join(json.dumps({"id": i, "rewrite": "y"}) for i in ids), encoding="utf-8")

    v = J.Verdict("B", "r", "m")
    monkeypatch.setattr(RJ, "judge_pair", lambda s, sig, oa, ob: J.PairResult("b", True, v, v))
    RJ.run(str(tmp_path / "s.jsonl"), str(tmp_path / "a.jsonl"), str(tmp_path / "b.jsonl"),
           str(tmp_path / "out"), "baseline", "run1")
    summary = json.loads((tmp_path / "out" / "judge_summary.json").read_text())
    assert summary["wins_run1"] == 3
    assert summary["wins_baseline"] == 0
    assert summary["win_rate_run1_vs_baseline"] == 1.0
    assert summary["position_bias_rate"] == 0.0

def test_neither_prompt_sees_the_signals(monkeypatch):
    secret = "SENTINEL-signal-label"
    signals = [{"model": "tone", "label": secret, "confidence": 0.9}]
    out = {"rewrite": "r", "notes": ["n"], "meaning": {"ask": "a"}}
    assert secret not in J.build_judge_prompt("Q: Coming?\nReply: Maybe.", signals, out, out)
    seen = []
    def fake(system, user, _retried=False):
        seen.append(system + user)
        return {"meaning_kept": 2, "clarity": 2, "warmth": 2, "notes_accurate": 2}
    monkeypatch.setattr(J, "_call", fake)
    J.score_output("Please send it.", signals, out)
    assert seen and secret not in seen[0]


def test_run_judge_never_hands_the_gold_rewrite_to_the_judge(monkeypatch, tmp_path):
    (tmp_path / "s.jsonl").write_text(json.dumps({"id": "1", "source": "s", "rewrite": "GOLD-SENTINEL",
                                                  "notes": ["GOLD-SENTINEL"]}), encoding="utf-8")
    (tmp_path / "a.jsonl").write_text(json.dumps({"id": "1", "rewrite": "x"}), encoding="utf-8")
    (tmp_path / "b.jsonl").write_text(json.dumps({"id": "1", "rewrite": "y"}), encoding="utf-8")
    seen = []
    v = J.Verdict("A", "r", "m")
    def fake(source, signals, out_a, out_b):
        seen.append(repr((source, signals, out_a, out_b)))
        return J.PairResult("a", True, v, v)
    monkeypatch.setattr(RJ, "judge_pair", fake)
    RJ.run(str(tmp_path / "s.jsonl"), str(tmp_path / "a.jsonl"), str(tmp_path / "b.jsonl"),
           str(tmp_path / "out"), "baseline", "run2")
    assert seen and "GOLD-SENTINEL" not in seen[0]


class _FakeClient:
    """Just enough of the OpenAI client: each create() answers the next content."""
    def __init__(self, contents):
        self.contents, self.calls = list(contents), 0
        self.chat = self.completions = self

    def create(self, **kwargs):
        from types import SimpleNamespace as NS
        self.calls += 1
        return NS(choices=[NS(message=NS(content=self.contents.pop(0)), finish_reason="length")])


def test_call_retries_once_on_empty_content_then_gives_up(monkeypatch):
    client = _FakeClient(["", '{"winner": "A", "reason": "x"}'])
    monkeypatch.setattr(J, "_client", lambda: client)
    assert J._call("s", "u") == {"winner": "A", "reason": "x"} and client.calls == 2
    client = _FakeClient(["", None, '{"winner": "B"}'])
    monkeypatch.setattr(J, "_client", lambda: client)
    with pytest.raises(J.JudgeError, match="no content after retry"):
        J._call("s", "u")
    assert client.calls == 2


def test_both_prompts_expect_a_reply_to_state_the_answer_it_implies():
    for prompt in (J.JUDGE_SYSTEM, J.SCORE_SYSTEM):
        assert "clearly implies" in prompt and "not settle" in prompt


def test_rubric_id_follows_the_judge_model_and_prompts():
    import hashlib
    expected = hashlib.sha256(f"{J.JUDGE_MODEL}\n{J.JUDGE_SYSTEM}\n{J.SCORE_SYSTEM}".encode()).hexdigest()[:12]
    assert J.RUBRIC_ID == expected


def test_run_judge_records_the_rubric_and_refuses_to_mix_rubrics(monkeypatch, tmp_path):
    for name, text in (("s", "s"), ("a", "x"), ("b", "y")):
        (tmp_path / f"{name}.jsonl").write_text(json.dumps({"id": "1", "source": text, "rewrite": text}), encoding="utf-8")
    v = J.Verdict("A", "r", "m")
    monkeypatch.setattr(RJ, "judge_pair", lambda s, sig, oa, ob: J.PairResult("a", True, v, v))
    args = (str(tmp_path / "s.jsonl"), str(tmp_path / "a.jsonl"), str(tmp_path / "b.jsonl"), str(tmp_path / "out"),
            "baseline", "run2")
    RJ.run(*args)
    pairs = [json.loads(l) for l in (tmp_path / "out/judge_pairs.jsonl").read_text().splitlines()]
    summary = json.loads((tmp_path / "out/judge_summary.json").read_text())
    assert pairs[0]["rubric"] == summary["rubric"] == J.RUBRIC_ID
    (tmp_path / "out/judge_pairs.jsonl").write_text(json.dumps({**pairs[0], "rubric": "oldrubric000"}) + "\n")
    with pytest.raises(SystemExit, match="another judge rubric"):
        RJ.run(*args)
