"""Automatic metrics for the Compose eval (CLAUDE.md, "Evaluation").

Scores one model's predictions on a gold set: the output of
`compose_client --input data/gold/<dataset>_gold.jsonl --out ...`.

    json_valid            share of messages with a usable answer
    entity_recall         share of the entities in the messages that the rewrites
                          kept: names, organisations, dates, times, amounts,
                          numbers and [TAGS], as the training filter and the
                          grounding check define them. Micro-averaged.
    nli_entailment        share of messages whose rewrite the NLI model reads as
                          entailed by the message
    grounded              share that pass the production grounding check
    added_entity_rate     share of rewrites with an entity the message doesn't have
    nli_contradiction     share of rewrites the NLI model reads as contradicting it
    circa_direct_rate     Circa only: share of rewritten replies the Circa
                          classifier reads as direct (the answer said outright)
    circa_answer_stated_rate  Circa only: share of rewritten replies that open with
                          the answer ("Yes, ...", "No, ...", "I can't ..."), as the
                          style guide's example does. The classifier is a weak
                          hint; this is the plain check.
    politeness_drop_rate  share where the politeness band falls (high -> medium...)
    politeness_to_low_rate  share where a message that wasn't blunt became blunt
    length_ratio          median words(rewrite) / words(message); the reply, for Circa

The first four count a message with no usable answer as a failure: it kept no
entities and entails nothing, so a model can't raise them by failing. The rest
describe the rewrites that were delivered, so they are over usable answers only.

The entity and NLI rules are the grounding check's own (grounding.py, which
imports them from the training filter), so the eval measures exactly what
serving enforces. Rates are 0-1 floats, None when there is nothing to rate.
"""
from __future__ import annotations

import re
import statistics
from typing import Any, Callable, Iterable, Mapping

from Src.source.data_prep import filter_pairs as fp

POLITENESS_ORDER = {"low": 0, "medium": 1, "high": 2}
ANSWER_FIRST = re.compile(r"\s*(?:yes|no|not yet|nope|yeah|sure|sorry,? (?:i|no)"
                          r"|i (?:can't|cannot|won't|don't|haven't|didn't))\b", re.I)

# The model-backed labellers, injectable so the tests need no models.
NliFn = Callable[[list[tuple[str, str]]], list[str]]
LabelFn = Callable[[str], str]


def usable(pred: Mapping[str, Any]) -> bool:
    """A prediction the service could show: no error, and a rewrite, notes and meaning."""
    return "error" not in pred and fp.check_json(dict(pred)) is None


def entity_counts(source: str, rewrite: str) -> tuple[int, int]:
    """(entities in the part of the message that gets rewritten, how many the
    rewrite kept). The part is the reply for Circa, as in fp.check_dropped."""
    ents = fp.entities(fp.split_circa(source)[1])
    rw_n, rw_t = fp.norm(rewrite), fp.tokens(rewrite)
    return len(ents), sum(fp.present(e, rewrite, rw_n, rw_t) for e in ents)


def nli_labels(pairs: list[tuple[str, str]]) -> list[str]:
    """Top NLI label for each (message, rewrite) pair: the grounding check's
    model, on the grounding check's device."""
    from Src.source.pipeline import grounding

    if not pairs:
        return []
    model, _ = grounding._nli_model()
    id2label = model.model.config.id2label
    names = [id2label[i].lower() for i in range(len(id2label))]
    return [names[int(s.argmax())] for s in model.predict(pairs, batch_size=32)]


def circa_label(reply: str) -> str:
    """The production Circa classifier on a reply alone, as compute_signals runs it."""
    from Src.source.pipeline.adapters import circa

    return circa.predict(reply)["label"]


def politeness_label(text: str) -> str:
    from Src.source.pipeline.adapters import politeness

    return politeness.predict(text)["label"]


def _labels(fn: LabelFn, texts: list[str], name: str) -> list[str]:
    out = [fn(t) for t in texts]
    if "unknown" in out:
        # The adapters degrade to "unknown" when their weights are missing. A
        # rate computed from that would look like a real result.
        raise RuntimeError(f"the {name} classifier answered 'unknown' - are its weights in models/?")
    return out


def score_predictions(gold: list[Mapping[str, Any]], preds: Mapping[str, Mapping[str, Any]], *,
                      nli: NliFn = nli_labels, circa: LabelFn = circa_label,
                      politeness: LabelFn = politeness_label) -> list[dict[str, Any]]:
    """One row per gold message with everything the metrics and worst-20 need.
    A gold id with no prediction counts as an unusable answer."""
    rows, ok = [], []
    for g in gold:
        p = preds.get(g["id"]) or {"error": "no prediction"}
        question, message = fp.split_circa(g["source"])
        row: dict[str, Any] = {"id": g["id"], "dataset": g.get("dataset"), "usable": usable(p),
                               "entities": len(fp.entities(message)), "kept": 0, "grounded": False}
        if row["usable"]:
            row["entities"], row["kept"] = entity_counts(g["source"], p["rewrite"])
            row["added"] = fp.check_added({"source": g["source"], "rewrite": p["rewrite"]}) is not None
            row["length_ratio"] = len(p["rewrite"].split()) / max(len(message.split()), 1)
            row["is_circa"] = question is not None
            ok.append((g, p, row))
        else:
            row["error"] = str(p.get("error") or fp.check_json(dict(p)))
        rows.append(row)

    for (_, _, row), label in zip(ok, nli([(g["source"], p["rewrite"]) for g, p, _ in ok])):
        row["nli"] = label
        # the grounding check's rule (grounding.check): nothing dropped, nothing
        # added, and the top NLI label isn't contradiction
        row["grounded"] = row["kept"] == row["entities"] and not row["added"] and label != "contradiction"

    circa_rows = [(p, row) for _, p, row in ok if row["is_circa"]]
    for (p, row), label in zip(circa_rows, _labels(circa, [p["rewrite"] for p, _ in circa_rows], "Circa")):
        row["circa_direct"] = label == "direct"
        row["circa_answer_stated"] = bool(ANSWER_FIRST.match(p["rewrite"]))
    sources = _labels(politeness, [fp.split_circa(g["source"])[1] for g, _, _ in ok], "politeness")
    rewrites = _labels(politeness, [p["rewrite"] for _, p, _ in ok], "politeness")
    for (_, _, row), s, r in zip(ok, sources, rewrites):
        row["politeness"] = [s, r]
    return rows


def _rate(flags: Iterable[bool]) -> float | None:
    flags = list(flags)
    return sum(flags) / len(flags) if flags else None


def summarize(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """The metrics over any set of rows: one dataset, or several pooled."""
    ok = [r for r in rows if r["usable"]]
    entities = sum(r["entities"] for r in rows)
    bands = [(POLITENESS_ORDER[s], POLITENESS_ORDER[r]) for s, r in (x["politeness"] for x in ok)]
    circa = [r["circa_direct"] for r in ok if "circa_direct" in r]
    return {
        "n": len(rows),
        "json_valid": _rate(r["usable"] for r in rows),
        "entity_recall": sum(r["kept"] for r in rows) / entities if entities else None,
        "nli_entailment": _rate(r.get("nli") == "entailment" for r in rows),
        "grounded": _rate(r["grounded"] for r in rows),
        "added_entity_rate": _rate(r["added"] for r in ok),
        "nli_contradiction": _rate(r["nli"] == "contradiction" for r in ok),
        "circa_direct_rate": _rate(circa),
        "circa_answer_stated_rate": _rate(r["circa_answer_stated"] for r in ok if "circa_answer_stated" in r),
        "politeness_drop_rate": _rate(r < s for s, r in bands),
        "politeness_to_low_rate": _rate(r == 0 and s != 0 for s, r in bands),
        "length_ratio": statistics.median(r["length_ratio"] for r in ok) if ok else None,
    }
