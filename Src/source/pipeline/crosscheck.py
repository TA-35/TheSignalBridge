"""Compares what the LLM read against what the rule-based extractor read.

The entity check catches the LLM inventing a fact from nowhere. It does not
catch the LLM *misreading* - taking a real phrase from the wrong part of the
message. If a message says the deadline is 10am Monday and the model reports
"week 14", every entity in that answer is present in the input, so the entity
check passes and the user is told the wrong deadline.

The extractor is the only independent reading available. It is not a better
reading - a single real email exposed five bugs in it - so a disagreement
does not mean the LLM is wrong. It means two methods looked at the same
sentence and came to different conclusions, and that is worth surfacing
rather than silently picking a winner.

Two ways to use the result:
  - as a quality signal when comparing runs (how often do they agree?)
  - as a UI hint: a deadline both agree on can be shown plainly, one they
    disagree about should be shown with the uncertainty visible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .analysis import Analysis

# Fields where disagreement actually matters to a reader. Getting `context`
# or `purpose` slightly differently is paraphrase; getting the deadline or
# the owner differently is a different instruction.
SIGNIFICANT_FIELDS: frozenset[str] = frozenset(
    {"deadline", "responsible_person", "required_action"}
)


@dataclass
class FieldComparison:
    field: str
    llm_text: str | None
    llm_span: tuple[int, int] | None
    extractor_text: str | None
    extractor_span: tuple[int, int] | None
    verdict: str  # agree | disagree | llm_only | extractor_only

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "verdict": self.verdict,
            "llm": {"text": self.llm_text, "span": list(self.llm_span)}
            if self.llm_span else None,
            "extractor": {"text": self.extractor_text,
                          "span": list(self.extractor_span)}
            if self.extractor_span else None,
        }


@dataclass
class CrossCheck:
    comparisons: list[FieldComparison] = field(default_factory=list)

    @property
    def disagreements(self) -> list[FieldComparison]:
        return [c for c in self.comparisons
                if c.verdict == "disagree" and c.field in SIGNIFICANT_FIELDS]

    @property
    def agreement_rate(self) -> float | None:
        both = [c for c in self.comparisons if c.verdict in {"agree", "disagree"}]
        if not both:
            return None
        return sum(c.verdict == "agree" for c in both) / len(both)

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparisons": [c.as_dict() for c in self.comparisons],
            "agreement_rate": self.agreement_rate,
            "disagreements": [c.field for c in self.disagreements],
        }


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """True if two spans share any characters.

    Overlap, not equality: the two methods bracket a clause differently by
    design. The extractor anchors after the request marker ("let us |know
    your level..."), while an LLM quotes the natural phrase ("let us know
    your level..."). Those are the same finding, and demanding identical
    offsets would report a disagreement on every single claim.
    """
    return a[0] < b[1] and b[0] < a[1]


def compare(
    claims: Iterable[Mapping[str, Any]], analysis: Analysis
) -> CrossCheck:
    """Compare resolved LLM claims against the extractor's own findings."""
    extraction = analysis.extraction

    by_field: dict[str, list[Mapping[str, Any]]] = {}
    for claim in claims:
        name = str(claim.get("field", "")).strip()
        span = claim.get("span")
        if not name or not isinstance(span, (list, tuple)) or len(span) != 2:
            continue
        by_field.setdefault(name, []).append(claim)

    extractor_fields: dict[str, tuple[str, tuple[int, int]]] = {
        name: (found.value, found.span)
        for name, found in extraction.found.items()
    }
    # Every ask, not just the first - otherwise a five-ask email reports four
    # false disagreements.
    extractor_actions = [(a.value, a.span) for a in extraction.actions]

    comparisons: list[FieldComparison] = []
    seen: set[str] = set()

    for name, field_claims in by_field.items():
        seen.add(name)
        candidates = (
            extractor_actions if name == "required_action"
            else ([extractor_fields[name]] if name in extractor_fields else [])
        )
        if not candidates:
            for claim in field_claims:
                comparisons.append(FieldComparison(
                    field=name, llm_text=str(claim.get("text")),
                    llm_span=tuple(claim["span"]), extractor_text=None,
                    extractor_span=None, verdict="llm_only"))
            continue

        for claim in field_claims:
            span = tuple(claim["span"])
            match = next(
                (c for c in candidates if _overlaps(span, c[1])), None
            )
            if match is not None:
                comparisons.append(FieldComparison(
                    field=name, llm_text=str(claim.get("text")), llm_span=span,
                    extractor_text=match[0], extractor_span=match[1],
                    verdict="agree"))
            else:
                nearest = candidates[0]
                comparisons.append(FieldComparison(
                    field=name, llm_text=str(claim.get("text")), llm_span=span,
                    extractor_text=nearest[0], extractor_span=nearest[1],
                    verdict="disagree"))

    for name, (value, span) in extractor_fields.items():
        if name not in seen:
            comparisons.append(FieldComparison(
                field=name, llm_text=None, llm_span=None,
                extractor_text=value, extractor_span=span,
                verdict="extractor_only"))

    return CrossCheck(comparisons=comparisons)
