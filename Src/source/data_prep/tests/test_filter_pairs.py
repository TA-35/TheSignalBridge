"""Tests for the gold guard and the test-data safety in filter_pairs.py.

The two near-copy pairs are the ones Sanket found in review
(enron_01523 -> enron_00006, enron_01556 -> enron_00021). The old MinHash
LSH at 0.85 let both through; the guard has to catch them now.
"""
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
fp = SourceFileLoader("filter_pairs", str(HERE.parent / "filter_pairs.py")).load_module()
PAIRS = json.loads((HERE / "fixtures" / "gold_near_copies.json").read_text())


@pytest.mark.parametrize("pair", PAIRS, ids=[f'{p["source_id"]}->{p["gold_id"]}' for p in PAIRS])
def test_gold_guard_catches_known_near_copies(pair):
    gold = [(pair["gold_id"], fp.shingles(pair["gold"]))]
    hit = fp.near_gold(pair["source"], gold)
    assert hit is not None, f"{pair['source_id']} should be flagged as a near copy of {pair['gold_id']}"
    assert hit[0] == pair["gold_id"]


def test_unrelated_message_is_not_flagged():
    gold = [(p["gold_id"], fp.shingles(p["gold"])) for p in PAIRS]
    assert fp.near_gold("Can we push the budget review to Tuesday afternoon instead?", gold) is None


def test_short_gold_does_not_swallow_longer_emails():
    gold = [("g", fp.shingles("Thanks!"))]
    long_email = "Thanks! I'll look over the pipeline numbers tonight and send my notes before the 9am call."
    assert fp.near_gold(long_email, gold) is None


def test_real_filter_refuses_test_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "generated").mkdir(parents=True)
    (tmp_path / "data" / "generated" / "test_gen.jsonl").write_text("{}\n")

    class Args:
        test = False; no_nli = True; allow_small = True

    with pytest.raises(SystemExit, match="refusing to run"):
        fp.step_filter(Args())


def _run_filter(tmp_path, monkeypatch, records, want):
    monkeypatch.chdir(tmp_path)
    gen = tmp_path / "data" / "generated"
    gen.mkdir(parents=True)
    (gen / "enron_gen.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")

    class Args:
        test = False; no_nli = True; allow_small = True; prompt_version = want

    fp.step_filter(Args())
    rej = [json.loads(l) for l in (tmp_path / "data/filtered/rejects.jsonl").read_text().splitlines() if l]
    ok = [json.loads(l) for l in (tmp_path / "data/filtered/train.jsonl").read_text().splitlines() if l]
    return ok, rej


def test_old_prompt_version_is_rejected(tmp_path, monkeypatch):
    base = {"dataset": "enron", "source": "please send the file", "signals": [],
            "meaning": {}, "rewrite": "Please send the file.", "notes": ["Made the request direct."]}
    records = [dict(base, id="a", prompt_version="abc123"), dict(base, id="b", prompt_version="old999")]
    ok, rej = _run_filter(tmp_path, monkeypatch, records, "abc123")
    assert [r["id"] for r in ok] == ["a"]
    assert rej[0]["id"] == "b" and rej[0]["check"] == "prompt_version"


def test_circa_only_checks_the_reply():
    src = "Q: Are you coming to the lunch at Nobu on Friday?\nReply: I'm swamped this week."
    r = {"source": src, "rewrite": "No, I can't come. I'm swamped this week."}
    assert fp.split_circa(src)[1] == "I'm swamped this week."
    assert fp.check_dropped(r) is None          # Nobu and Friday live in the question
    assert fp.check_length(r) is None           # 9 vs 4 words is fine against the reply
