"""The flagged-message rule and selection targets, shared by every dataset.

Enron, Stanford and Circa each pick 850 flagged / 150 clear source messages
and 45 / 15 gold. "Flagged" has to mean the same thing in all three, or the
training mix silently differs by dataset - so the rule lives here once and
every step-1 script imports it instead of keeping a copy.

Flagged (needs a rewrite), per the plan: politeness low OR high (over-polite
is just as unclear), circa indirect, or a hedge phrase anywhere in the
message. Clear = none of those. Tone is an input signal only, never a flag.

Moved here unchanged from enron_step1.py (#13) and stanford_step1.py (#23),
which had identical copies. One behaviour is new and only affects Circa:
for a "Q: ... / Reply: ..." source the hedge search looks at the reply, the
part that gets rewritten, so a hedge in the question no longer flags it.
Every other source behaves exactly as before.

Standard library only (plus compose_prompt, which is too), so any data
script can import it without the pipeline's dependencies. compute_signals()
imports the adapters lazily, only when it is called.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from Src.source.pipeline import compose_prompt as cp

FLAG_RULES = {"politeness": {"low", "high"}, "circa": {"indirect"}}
HEDGES = re.compile(
    r"if you get a chance|when you get a chance|if you have a (?:minute|moment|sec)|when you have a (?:minute|moment|sec)"
    r"|just (?:wondering|checking|curious|a thought|a heads up)|i was wondering|wondering if"
    r"|circle back|touch base|might be worth|may be worth|could be worth|worth a look"
    r"|no rush,? but|no pressure,? but|not urgent,? but|whenever you can|at your convenience"
    r"|would be (?:great|nice|good) if|it might be (?:good|nice|helpful)|you (?:may|might) want to"
    r"|perhaps we could|maybe we could|not sure if|if (?:possible|you can|you could)|could you possibly",
    re.I)

# Selection targets, identical for every dataset.
SEED = 42
N_GOLD_FLAGGED, N_GOLD_CLEAR = 45, 15
N_RES_FLAGGED, N_RES_CLEAR = 30, 10
N_SRC_FLAGGED, N_SRC_CLEAR = 850, 150


def rewritten_text(source: str) -> str:
    """The part of a source that gets rewritten: the reply for Circa, else all of it."""
    return cp.split_circa(str(source))[1]


def flag_reasons(record: Mapping[str, Any]) -> list[str]:
    """Why a record is flagged, e.g. ["hedge", "politeness=high"]; [] means clear."""
    reasons = []
    if HEDGES.search(rewritten_text(record.get("source", ""))):
        reasons.append("hedge")
    for s in record.get("signals") or []:
        label = str(s.get("label", "")).lower()
        if s.get("model") in FLAG_RULES and label in FLAG_RULES[s["model"]]:
            reasons.append(f"{s['model']}={label}")
    return reasons


def is_flagged(record: Mapping[str, Any]) -> bool:
    return bool(flag_reasons(record))


def compute_signals(text: str) -> list[dict[str, Any]]:
    """The three frozen adapters on `text`, in the exact shape training uses.

    Pass the part that gets rewritten - for Circa that is the reply alone,
    with no question, because that is all production sees. A classifier that
    fails comes back as {"label": "unknown", "confidence": 0.0}, never null.
    Needs the pipeline's dependencies and the tone weights in
    models/enron_register_distilbert/.
    """
    from Src.source.pipeline.adapters import circa, politeness, tone  # noqa: E402 - heavy, lazy

    return cp.clean_signals([tone.predict(text), politeness.predict(text), circa.predict(text)])


def split_counts(records: Iterable[Mapping[str, Any]]) -> tuple[int, int]:
    """(flagged, clear) counts, for checking a finished file against the targets."""
    flags = [is_flagged(r) for r in records]
    return sum(flags), len(flags) - sum(flags)
