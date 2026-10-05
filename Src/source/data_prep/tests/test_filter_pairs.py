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
