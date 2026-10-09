"""Grounding check for a Compose rewrite: nothing dropped, nothing added,
nothing contradicted.

A rewrite that fails is never shown (docs/api-contract.md, POST /api/compose):
it reads as finished text and would be pasted straight into an email. The
service retries once at a lower temperature, and otherwise answers with
rewrite = null and the failure classes from `reasons`.

The checks are the training filter's (data_prep/filter_pairs.py), imported
rather than copied, so the model is held at serving time to exactly the rule
its training data passed:

    entities_kept     every name, organisation, date, time, amount, number and
                      [PLACEHOLDER] in the message is still in the rewrite
    nothing_added     the rewrite has none the message doesn't
    no_contradiction  NLI (cross-encoder/nli-deberta-v3-base) doesn't read the
                      rewrite as contradicting the message

NLI only runs once both entity checks pass; a rewrite that already failed
doesn't need it. Call warm_up() at startup, or the first check pays for
loading spaCy and the cross-encoder. If a check can't run at all the rewrite
counts as unverified and fails - never the other way round.

Never logs or returns message text: `reasons` are fixed class names.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from Src.source.data_prep import filter_pairs as fp

DROPPED = "dropped_entity"
ADDED = "added_entity"
CONTRADICTION = "contradiction"
UNAVAILABLE = "check_unavailable"

_nli = None
_nli_lock = threading.Lock()


@dataclass(frozen=True)
class Grounding:
    entities_kept: bool
    nothing_added: bool
    no_contradiction: bool | None       # None: not run, because an entity check failed
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.reasons

    def checks(self) -> dict[str, bool | None]:
        """The `checks` object of an undegraded /api/compose answer."""
        return {"entities_kept": self.entities_kept, "nothing_added": self.nothing_added,
                "no_contradiction": self.no_contradiction}


def _nli_model():
    """The cross-encoder and the index of its "contradiction" label, loaded once."""
    global _nli
    with _nli_lock:
        if _nli is None:
            from sentence_transformers import CrossEncoder
            model = CrossEncoder(fp.NLI_MODEL)
            id2label = model.model.config.id2label
            labels = [id2label[i].lower() for i in range(len(id2label))]
            _nli = (model, labels.index("contradiction"))
    return _nli


def warm_up() -> None:
    """Load spaCy and the NLI model now. Raises if either is missing: better a
    service that won't start than one that can never verify a rewrite."""
    fp.nlp()
    _nli_model()


def contradicts(source: str, rewrite: str) -> bool:
    """The filter's NLI rule: the top label for (message, rewrite) is contradiction."""
    model, contradiction = _nli_model()
    return int(model.predict([(source, rewrite)])[0].argmax()) == contradiction


def check(source: str, rewrite: str) -> Grounding:
    record = {"source": source, "rewrite": rewrite}
    try:
        kept = fp.check_dropped(record) is None
        nothing_added = fp.check_added(record) is None
        consistent = (not contradicts(source, rewrite)) if kept and nothing_added else None
    except Exception:  # noqa: BLE001 - an unverified rewrite fails, whatever broke
        return Grounding(False, False, None, (UNAVAILABLE,))
    reasons = []
    if not kept:
        reasons.append(DROPPED)
    if not nothing_added:
        reasons.append(ADDED)
    if consistent is False:
        reasons.append(CONTRADICTION)
    return Grounding(kept, nothing_added, consistent, tuple(reasons))
