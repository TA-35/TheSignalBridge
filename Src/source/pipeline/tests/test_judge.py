"""Eval judge logic tests. _call is faked, so no API key or network is needed."""
import json
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