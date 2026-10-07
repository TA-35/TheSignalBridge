# Library Dataset Card: Pattern Library (60 Cards)

## 1. Overview

This dataset is 60 curated pattern-library cards, matching the backend `Pattern` schema
(`id`, `name`, `category`, `implies`, `why_misread`), built for ReadTheRoom's Pattern
library / flashcard feature.

**This is not the output of a model auto-classifying or auto-generating text.** It is the
product of a curated pipeline: rule-based candidate screening against a real corpus, manual
selection, LLM-assisted drafting of the `implies`/`why_misread` copy, and human review of every
card before export.

## 2. Provenance

- **10 cards** are real-corpus-derived, sourced from `stanford_politeness_features.csv`
  (Stanford Politeness Corpus, see `DATA_CARD.md`). Each retains its original `Id` and
  `Normalized Score` in the working notebook (`Library_Dataset.ipynb`) as a traceability record,
  even though those fields aren't part of the exported JSON schema. All 10 belong to the
  `Softened request` category.
- **50 cards** are hand-designed by the team, not derived from any external dataset. They cover
  the remaining 5 categories at 10 cards each.
- **Why 10:50:** the Stanford Politeness Corpus only annotates politeness /
  indirectness. It has no deadline, ownership, priority, or scope annotations, so it can only
  support the `Softened request` category. This is a domain limitation of the source corpus, not
  a sampling choice.

## 3. Theoretical Basis (Category Design)

**Vagueness vs. incompleteness.** `Vague deadline`, `Unclear priority`, and `Undefined scope`
are grounded in what Daniel M. Berry ("Ambiguity in Natural Language Requirements Documents",
University of Waterloo) calls **vagueness**: a category with no clear boundary between what
satisfies it and what doesn't — his own example is *fast*, which "has no clear boundary between
fast and not fast." `Unassigned owner` is a different defect type: information that is simply
missing (who owns it), not information that is present but fuzzy. This is **not** part of
Berry's ambiguity taxonomy — his taxonomy tree is Vagueness / Generality / Linguistic Ambiguity /
Software Engineering Ambiguity, with no "incompleteness" branch. Missing-information defects are
instead the other of the two SRS quality criteria IEEE 830 lists separately: "unambiguous" and
"complete." So `Unassigned owner` is grounded in IEEE 830's completeness criterion, not in
Berry's ambiguity framework.

**Softened request / Feedback framing.** These draw on Danescu-Niculescu-Mizil et al. (2013,
ACL), "A computational approach to politeness with application to social factors," and on
Grice's Cooperative Principle (conversational implicature) — a softened or positively-framed
message routinely says less than it means, relying on the hearer to infer the actual content.

**Methodological precedent.** Mannekote, Nam, Li, Gao, Boyer, and Dorr, "Making Task-Oriented
Dialogue Datasets More Natural by Synthetically Generating Indirect User Requests" (arXiv
2406.07794; COLING 2025), propose linguistic criteria paired with an LLM-based pipeline to
generate realistic indirect-request examples for testing dialogue systems. This is a published
precedent for the same general approach used here — real-corpus screening plus
linguistically-motivated, LLM-assisted example generation plus human review — as an accepted
methodology in this research area, not an ad hoc substitute for a trained classifier.

## 4. Category-to-Theory Mapping

| Category | Theoretical Basis |
|---|---|
| Softened request | Politeness theory (negative-politeness strategies) + Grice's maxims |
| Vague deadline | Berry's vagueness (present-but-fuzzy) |
| Unclear priority | Berry's vagueness (present-but-fuzzy) |
| Undefined scope | Berry's vagueness (present-but-fuzzy) |
| Unassigned owner | IEEE 830 incompleteness (present-but-missing) |
| Feedback framing | Politeness theory (positive-politeness framing) |

## 5. Softened Request Candidate Selection Method

Candidates were pulled from `stanford_politeness_features.csv` with a fixed, reproducible
filter: `hedge_wordlist` OR `please` OR `counterfactual_modal` is `True` (at least one softening
marker), AND `is_high_disagreement` is `False` AND `is_too_short` is `False` (excluding
low-quality samples flagged in the source dataset). Candidates were then sorted by descending
`Normalized Score` and reviewed manually. This is a rule-based filter with a fixed,
inspectable definition — not a model classifying requests into the category.

## 6. Writing Style Specification

### Tone: Low-pressure, guiding

Target reader: someone who may feel anxious about not understanding a message's subtext. Tone
should read like a knowledgeable friend "translating" the message, not a system analyzing or
correcting.

**implies field:**
- Opens with one of: "This usually means...", "There's likely a...", "Often, this signals..."
  (varied across cards, not repeated identically each time)
- Describes what the message is likely intended to convey

**why_misread field:**
- Opens with one of: "It's easy to read this as...", "You might take ...at face value as..."
- Names the literal/surface reading first, then explains where the real information usually
  lives (context, relationship, tone — not the literal words)

**Hard constraints (apply to both implies and why_misread):**
- No em-dashes (— or --). Use two sentences (period break) or natural connectors (so/and/but)
  instead.
- Each field kept to roughly 30 words or fewer
- No judgmental language toward either sender or receiver
- No clinical/"pointing-out" phrasing (e.g. avoid openings like "Read literally...")
- The `name` field is exempt from the em-dash rule — original candidate text or corpus text is
  preserved as-is

**Important attribution note:** these tone/style rules are a team design decision made
collaboratively during Stage 3, calibrated through 3 example cards before full-scale drafting.
They are not derived from any of the theoretical sources in Section 3.
The category framework is theory-grounded and citable; the tone is a product/UX choice the team
made and owns.

## 7. Schema

| Field | Type | Description |
|---|---|---|
| `id` | integer | Card's unique identifier, 1-60. Existing IDs 1-25 were retained during expansion. |
| `name` | string | The full message text being interpreted — the literal sentence a reader might receive. |
| `category` | string | One of exactly 6 fixed values: `Softened request`, `Vague deadline`, `Unassigned owner`, `Unclear priority`, `Undefined scope`, `Feedback framing`. |
| `implies` | string | The message's likely intended meaning, in low-pressure guiding tone. |
| `why_misread` | string | Why the literal reading is an easy, understandable mistake, and where the real information usually is. |

## 8. Known Limitations

- **60 cards is a curated set, not a statistically representative sample.** It should not be used
  for statistical inference about how often any pattern occurs in real communication.
- **Berry's ambiguity theory was developed for software requirements documents**, not
  interpersonal workplace messages. Applying it here is a cross-domain analogy, resting on the
  judgment that vagueness's core definition (no clear boundary) is a general linguistic feature
  that transfers across domains. That transfer has not been independently validated.
- **The tone rules in Section 6 are a team-calibrated product decision**, not tested against real
  users. They represent the team's current understanding of "low-pressure, guiding," not a
  validated effective tone.
- **Some `Unassigned owner` cards have semantic overlap with vagueness.** Phrasing like
  "and it may be you" sits slightly between pure incompleteness and vagueness. This was reviewed
  and accepted as usable during Stage 3 human review, but these aren't textbook-clean examples of
  the theoretical distinction in Section 3.

## 9. Version Info

- **Original version:** 2026-09-01 (25 cards)
- **Expanded:** 2026-10-07 (60 cards)
- **Notebook:** `Library_Dataset.ipynb`
- **Output files:** `library_dataset.json`, `library_dataset_preview.md`
- **Total cards:** 60
- **Expansion rule:** Retain IDs 1-25 unchanged; append IDs 26-60.
