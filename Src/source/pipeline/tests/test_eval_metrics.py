"""Eval metric tests. Entities use the real spaCy model, as the filter's tests
do; NLI and the two classifiers are faked."""
from __future__ import annotations

import pytest

from Src.source.pipeline import eval_metrics as em
from Src.source.pipeline import grounding

pytest.importorskip("spacy")
try:
    em.fp.nlp()
except OSError:
    pytest.skip("en_core_web_sm not installed", allow_module_level=True)

MSG = "Please send [NAME] the 4 reports by 10:30."
CIRCA = "Q: Can you cover my shift on Saturday?\nReply: I would if I could."


def pred(rewrite):
    return {"rewrite": rewrite, "notes": ["Made the ask explicit."], "meaning": {"ask": "send the reports"}}


def fake_nli(verdicts):
    """NLI answering from {rewrite: label}, entailment for anything else."""
    return lambda pairs: [verdicts.get(rw, "entailment") for _, rw in pairs]


def run(gold, preds, nli=None, circa=None, politeness=None):
    return em.score_predictions(gold, preds, nli=nli or fake_nli({}),
                                circa=circa or (lambda text: "direct"),
                                politeness=politeness or (lambda text: "medium"))


def test_entity_recall_counts_each_entity_and_a_failed_answer_keeps_none():
    n = len(em.fp.entities(MSG))
    assert n >= 3                                   # [NAME], 4, 10:30
    gold = [{"id": i, "source": MSG} for i in "abc"]
    rows = run(gold, {"a": pred("Please send [NAME] the 4 reports by 10:30 today."),
                      "b": pred("Please send [NAME] the reports by 10:30."),
                      "c": {"error": "ComposeOutputError: reply isn't JSON"}})
    assert [r["kept"] for r in rows] == [n, n - 1, 0]
    metrics = em.summarize(rows)
    assert metrics["entity_recall"] == pytest.approx((2 * n - 1) / (3 * n))
    assert metrics["json_valid"] == pytest.approx(2 / 3)


def test_a_gold_message_without_a_usable_prediction_counts_as_a_failure():
    rows = run([{"id": "a", "source": MSG}, {"id": "b", "source": MSG}],
               {"b": {"rewrite": "Please send [NAME] the 4 reports by 10:30.", "notes": ["n"]}})  # no meaning
    assert [r["usable"] for r in rows] == [False, False]
    assert em.summarize(rows)["json_valid"] == 0 and em.summarize(rows)["grounded"] == 0


def test_grounded_is_the_grounding_checks_rule(monkeypatch):
    rewrites = {"ok": "Please send [NAME] the 4 reports by 10:30 today.",
                "dropped": "Please send [NAME] the reports by 10:30.",
                "added": "Please send [NAME] the 4 reports by 10:30 on Friday.",
                "contradicted": "Don't send [NAME] the 4 reports by 10:30."}
    verdicts = {rewrites["contradicted"]: "contradiction"}
    monkeypatch.setattr(grounding, "contradicts", lambda source, rewrite: verdicts.get(rewrite) == "contradiction")
    rows = run([{"id": k, "source": MSG} for k in rewrites], {k: pred(v) for k, v in rewrites.items()},
               nli=fake_nli(verdicts))
    assert {r["id"]: r["grounded"] for r in rows} == {k: grounding.check(MSG, v).ok for k, v in rewrites.items()}
    assert [r["grounded"] for r in rows] == [True, False, False, False]


def test_entailment_counts_failed_answers_contradiction_is_over_answers_only():
    gold = [{"id": i, "source": MSG} for i in "abcd"]
    preds = {"a": pred("A"), "b": pred("B"), "c": pred("C"), "d": {"error": "timeout"}}
    metrics = em.summarize(run(gold, preds, nli=fake_nli({"B": "neutral", "C": "contradiction"})))
    assert metrics["nli_entailment"] == pytest.approx(1 / 4)
    assert metrics["nli_contradiction"] == pytest.approx(1 / 3)


def test_circa_direct_rate_is_over_circa_replies_only():
    seen = []

    def circa(text):
        seen.append(text)
        return "direct" if text.startswith("No") else "indirect"

    gold = [{"id": "c1", "source": CIRCA}, {"id": "c2", "source": CIRCA}, {"id": "e", "source": MSG}]
    rows = run(gold, {"c1": pred("No, I can't cover your shift on Saturday."), "c2": pred("I would if I could."),
                      "e": pred("Please send [NAME] the 4 reports by 10:30.")}, circa=circa)
    assert seen == ["No, I can't cover your shift on Saturday.", "I would if I could."]
    assert em.summarize(rows)["circa_direct_rate"] == 0.5
    assert em.summarize([r for r in rows if r["id"] == "e"])["circa_direct_rate"] is None
    assert em.summarize(rows)["circa_answer_stated_rate"] == 0.5         # "No, ..." states it; the other doesn't


@pytest.mark.parametrize("rewrite, stated", [
    ("No, I can't cover your shift on Saturday.", True), ("Yes, when it's about dragons.", True),
    ("I can't make it, sorry.", True), ("Not yet. I still have a lot to do.", True),
    ("I would if I could.", False), ("Nothing much, I might just go home.", False), ("Notably busy.", False),
    ("I would if I could, but sadly no.", False),
])
def test_answer_stated_means_the_reply_opens_with_the_answer(rewrite, stated):
    rows = run([{"id": "c", "source": CIRCA}], {"c": pred(rewrite)})
    assert rows[0]["circa_answer_stated"] is stated


def test_politeness_drop_and_becoming_blunt():
    bands = {"m1": "high", "r1": "medium", "m2": "medium", "r2": "low",
             "m3": "low", "r3": "low", "m4": "medium", "r4": "high"}
    rows = run([{"id": str(i), "source": f"m{i}"} for i in range(1, 5)],
               {str(i): pred(f"r{i}") for i in range(1, 5)}, politeness=lambda text: bands[text])
    metrics = em.summarize(rows)
    assert metrics["politeness_drop_rate"] == 0.5        # high -> medium, medium -> low
    assert metrics["politeness_to_low_rate"] == 0.25     # only medium -> low turned blunt


def test_length_ratio_is_against_the_reply_for_circa():
    rows = run([{"id": "c", "source": CIRCA}], {"c": pred("No, I can't cover your shift on Saturday.")})
    assert em.summarize(rows)["length_ratio"] == pytest.approx(8 / 5)


def test_a_classifier_without_weights_stops_the_eval():
    with pytest.raises(RuntimeError, match="politeness"):
        run([{"id": "a", "source": MSG}], {"a": pred("x")}, politeness=lambda text: "unknown")
    with pytest.raises(RuntimeError, match="Circa"):
        run([{"id": "c", "source": CIRCA}], {"c": pred("No.")}, circa=lambda text: "unknown")
