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


# The next four come from the teacher bake-off, where good DeepSeek pairs were
# rejected: "end of month" kept as "...the end of the month." read as dropped
# because the token was "month.", and a stated "no" to a 5-word Circa reply
# went over 2.5x.

def test_tokens_drop_sentence_end_punctuation_only():
    t = fp.tokens("Timesheets are due at the end of the month. Call at 10:00 on 02/06/02, it costs $3.50.")
    assert {"month", "10:00", "02/06/02", "$3.50"} <= t
    assert not any(w.endswith(".") for w in t)


def test_entity_closing_a_sentence_still_counts_as_kept():
    rw = "Timesheets are due at the end of the month."
    assert fp.present("end of month", rw, fp.norm(rw), fp.tokens(rw))
    gone = "Timesheets are due soon."
    assert not fp.present("end of month", gone, fp.norm(gone), fp.tokens(gone))


def test_short_circa_reply_can_state_the_answer():
    r = {"source": "Q: Can you cover my shift on Saturday?\nReply: I would if I could.",
         "rewrite": "Sorry, I can't cover your shift on Saturday. I would if I could."}
    assert fp.check_length(r) is None           # 13 vs 5 words: over 2.5x, inside +12


def test_length_limits_still_hold():
    five = "I would if I could."
    assert fp.check_length({"source": five, "rewrite": " ".join(["word"] * 18)})       # 5 + 12 = 17 max
    forty = " ".join(["word"] * 40)
    assert fp.check_length({"source": forty, "rewrite": " ".join(["word"] * 101)})     # 2.5 x 40 = 100 max
    assert fp.check_length({"source": forty, "rewrite": " ".join(["word"] * 19)})      # under 0.5x


# Run 1's filter still rejected some good pairs for their form, not their
# meaning: a numbered list turned into bullets, a typo fixed, an article
# added, "FYI" dropped. The live grounding check shares these rules.

def test_numbered_list_turned_into_bullets_keeps_its_entities():
    r = {"source": "Attached are drafts for:\n(1) Short cover letter\n2) Draft proposal\n3. Draft confirmation form",
         "rewrite": "Attached are drafts for:\n- Short cover letter\n- Draft proposal\n- Draft confirmation form"}
    assert fp.check_dropped(r) is None and fp.check_added(r) is None


def test_numbers_in_the_text_are_still_checked():
    r = {"source": "Please send the 3 drafts by Friday.", "rewrite": "Please send the drafts by Friday."}
    assert fp.check_dropped(r) is not None


def test_a_spelling_fix_is_not_an_added_date():
    r = {"source": "I will stop by and visit you tommorow.", "rewrite": "I will stop by and visit you tomorrow."}
    assert fp.check_added(r) is None


def test_articles_do_not_make_a_date_look_dropped():
    rw = "Please finish it by the end of the week."
    assert fp.present("the end of week", rw, fp.norm(rw), fp.tokens(rw))
    other = "Please finish it soon."
    assert not fp.present("the end of week", other, fp.norm(other), fp.tokens(other))


def test_fyi_is_not_an_entity():
    r = {"source": "FYI the meeting moved to Room 4.", "rewrite": "The meeting moved to Room 4."}
    assert fp.check_dropped(r) is None


def test_hedge_next_to_a_deadline_is_rejected():
    r = {"rewrite": "No rush, but could you send the deck before Thursday's meeting?",
         "meaning": {"deadline": "before Thursday's meeting"}}
    assert fp.check_hedge_kept(r) is not None
    r["rewrite"] = "Could you send the deck before Thursday's meeting?"
    assert fp.check_hedge_kept(r) is None


def test_no_rush_without_a_deadline_is_real_urgency_and_stays():
    r = {"rewrite": "No rush. Could you send me the deck when it's ready?", "meaning": {"deadline": ""}}
    assert fp.check_hedge_kept(r) is None


# Live Compose withheld good rewrites of casual messages for their form, not
# their meaning: "b4" read as the number 4, "if you have a sec" as a time, and
# "2 things" written out as "two things" as a dropped number.

def test_texting_shorthand_is_not_a_number():
    r = {"source": "hey can u check the budget numbers b4 thursday, the client wants them early if possible",
         "rewrite": "Hey, can you check the budget numbers before Thursday? The client wants them early if possible."}
    assert fp.check_dropped(r) is None and fp.check_added(r) is None
    r = {"source": "can we meet 2moro?", "rewrite": "Can we meet tomorrow?"}
    assert fp.check_dropped(r) is None and fp.check_added(r) is None
    r = {"source": "pls review the draft b4 friday, gr8 thx", "rewrite": "Please review the draft before Friday. Thanks!"}
    assert fp.check_dropped(r) is None and fp.check_added(r) is None


def test_shorthand_does_not_hide_a_dropped_date():
    r = {"source": "check the numbers b4 thursday", "rewrite": "Check the numbers soon."}
    assert fp.check_dropped(r) is not None


# Found by the 100-message Compose test (2026-10-12): these drafts got no
# rewrite at all. "sum1" holds a 1, and "tmrw", "this arvo" and "last yr"
# spelled out read as an added date or time.

@pytest.mark.parametrize("source, rewrite", [
    ("can sum1 grab the parcel from the post office b4 it closes? im stuck at work rn",
     "Can someone grab the parcel from the post office before it closes? I'm stuck at work right now."),
    ("if anyone can cover the front desk 12-1 tmrw that'd be amazing",
     "If anyone can cover the front desk from 12 to 1 tomorrow, that would be amazing."),
    ("Whoever is free this arvo, can you give the new starter a hand with their laptop setup?",
     "Whoever is free this afternoon, can you help the new starter set up their laptop?"),
    ("might be worth booking the tix soon, they sold out in like a day last yr",
     "It might be worth booking the tickets soon. They sold out in about a day last year."),
    # spaCy tags "tidy ur floor" as a name
    ("Jamie ur room is a disaster. pls tidy ur floor, make ur bed and take the dirty plates down b4 nana gets here.",
     "Jamie, your room is a mess. Please tidy your floor, make your bed and take the dirty plates down before Nana gets here."),
])
def test_more_texting_shorthand_passes(source, rewrite):
    r = {"source": source, "rewrite": rewrite}
    assert fp.check_dropped(r) is None and fp.check_added(r) is None


def test_spelled_out_shorthand_still_keeps_the_date():
    r = {"source": "can u cover the desk tmrw", "rewrite": "Can you cover the desk next week?"}
    assert fp.check_dropped(r) is not None


def test_a_sec_is_a_hedge_not_a_time():
    r = {"source": "Might be worth double-checking the budget figures with finance, if you have a sec.",
         "rewrite": "Could you double-check the budget figures with finance?"}
    assert fp.check_dropped(r) is None
    timed = {"source": "The call starts in 10 minutes.", "rewrite": "The call starts soon."}
    assert fp.check_dropped(timed) is not None


def test_a_number_written_out_is_the_same_number():
    r = {"source": "need 2 things fixed before the demo", "rewrite": "I need two things fixed before the demo."}
    assert fp.check_dropped(r) is None and fp.check_added(r) is None
    r["rewrite"] = "I need three things fixed before the demo."
    assert fp.check_dropped(r) is not None
