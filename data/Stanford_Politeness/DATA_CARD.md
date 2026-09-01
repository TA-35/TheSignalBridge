# Data Card: Stanford Politeness Corpus (Cleaned Subset)

## Source

- **Dataset:** Stanford Politeness Corpus v1.01 (released May 2013)
- **Original paper:** Cristian Danescu-Niculescu-Mizil, Moritz Sudhof, Dan Jurafsky, Jure Leskovec, Christopher Potts. "A computational approach to politeness with application to social factors." Proceedings of ACL, 2013.
- **Original files (6 CSVs):** `wikipedia.requests.csv`, `wikipedia.annotated.csv`, `wikipedia.admins.csv`, `stack-exchange.requests.csv`, `stack-exchange.annotated.csv`, `stack-exchange.roles.csv`
- **Files actually used for this cleaned dataset:** `wikipedia.annotated.csv` and `stack-exchange.annotated.csv` only — these are the subsets with politeness annotations (`Normalized Score`) and were confirmed in Stage 1 to have zero missing values.
- **License:** CC BY 4.0. Per ConvoKit documentation: "ConvoKit's Stanford Politeness Corpus is governed by the CC BY license v4.0. Copyright (C) 2017-2020 The ConvoKit Developers." (https://convokit.cornell.edu/documentation/wiki_politeness.html)

## Processing Steps

**Stage 1 — Explore**
- Loaded all 6 original CSVs; checked shape, columns, and missing values for each.
- Confirmed row counts against `Readme.txt`: Wikipedia 35,661 requests / 4,353 annotated; Stack Exchange 373,519 requests / 6,603 annotated — all four counts matched exactly.
- Checked annotator agreement across the 5 raw `Score1`–`Score5` ratings (per-row standard deviation, pairwise correlation between annotators).
- Reviewed the distribution of `Normalized Score` for both sources.

**Stage 2 — Clean**
a) Kept only `Id`, `Request`, `Normalized Score`, `Community` from the two `.annotated.csv` files.
b) Computed `disagreement_std` (standard deviation across the 5 annotators' raw scores per request) and flagged `is_high_disagreement` using a **mean + 2·standard-deviation** threshold, computed separately per source (Wikipedia and Stack Exchange each got their own threshold).
c) Cleaned `Request` text: collapsed embedded newlines/carriage returns to a single space, and normalized repeated whitespace to a single space.
d) Removed markup contamination, detected first and then cleaned only on confirmed patterns:
   - Wikipedia: `'''bold'''` and `''italic''` — markers stripped, inner text kept. `{{templates}}` — removed entirely (braces and content). Leftover HTML-ish tags (`<nowiki>`, `<big>`, `<span>`, `<br>`, etc.) — tag stripped, inner text kept.
   - Stack Exchange: backtick-wrapped code (`` `code` ``) — removed entirely, backticks and content both. Real HTML tags (`<div>`, `<a>`, `<img>`, `<br>`) — tag stripped and inner text kept; tags with no inner text removed entirely. Markdown `**bold**`, `*italic*` — markers stripped, inner text kept. `[text](url)` — kept `text`, dropped the URL.
   - `<url>` and `<person>` placeholder tokens (Wikipedia anonymization markers) were left untouched throughout — these are intentional redactions in the original corpus, not contamination.
e) Computed `is_too_short` (Request has fewer than 5 words OR fewer than 20 characters after cleaning), computed on the final cleaned text, uniformly across both sources.
f) Found during Stage 4 feature-engineering prep (not in the original Stage 2 pass): 5 Wikipedia rows still began with leftover wikitext table markup (`|style="..." |` or `|}`). Stripped this leading table-cell syntax and re-normalized whitespace.
g) Also found during Stage 4 prep: 15 rows (14 Wikipedia, 1 Stack Exchange) contained HTML character entities (`&mdash;`, `&amp;`, numeric entities such as `&#12395;`, etc.), and 1 Wikipedia row contained `[[wikilink|display text]]` syntax. Decoded entities with Python's standard `html.unescape`; replaced `[[Target]]` with `Target` and `[[Target|Display]]` with `Display`.

**Stage 3 — Export**
- Exported the resulting dataframe to `stanford_politeness_clean.csv`.
- Re-read the CSV from disk and verified row count, column count, and dtypes (including that both boolean flag columns read back as `bool`, not strings).

**Stage 4 — Feature Engineering**
- Added 21 boolean politeness-marker feature columns to `clean_df`. Full detail in the [Feature Engineering (Stage 4)](#feature-engineering-stage-4) section below.

**Stage 5 — Export (features)**
- Exported the feature-augmented dataframe to `stanford_politeness_features.csv`, alongside (not replacing) `stanford_politeness_clean.csv`.
- Re-read the CSV from disk and verified shape and that all 21 feature columns read back as `bool`.

## Schema

| Column | Type | Description |
|---|---|---|
| `Id` | int | Unique ID of the request (matches the ID in the original per-source `.requests.csv` file). |
| `Community` | string | Original source-level community label: `"Wikipedia"` for all Wikipedia rows, or the specific StackExchange sub-community (e.g. `"092011 Stack Overflow"`, `"092011 Cooking"`) for Stack Exchange rows. |
| `source` | string | Coarse-grained source tag: `"wikipedia"` or `"stack-exchange"`. |
| `Request` | string | Cleaned request text (whitespace-normalized, markup removed per the rules above). |
| `Normalized Score` | float | Politeness score, normalized per-annotator, as provided by the original corpus. |
| `disagreement_std` | float | Standard deviation across the 5 original annotators' raw `Score1`–`Score5` ratings for this request. |
| `is_high_disagreement` | bool | `True` if `disagreement_std` exceeds mean + 2·std **within its own source** (Wikipedia and Stack Exchange thresholds computed separately). This is a **flag, not a filter** — no rows were removed based on it. |
| `is_too_short` | bool | `True` if the cleaned `Request` has fewer than 5 words or fewer than 20 characters. This is a **flag, not a filter** — no rows were removed based on it. |

The dataset has **10,956 rows** total (4,353 Wikipedia + 6,603 Stack Exchange), matching the original annotated-file counts exactly — no rows were dropped at any point in Stage 2 or Stage 3.

## Feature Engineering (Stage 4)

### Feature source

- 20 politeness strategies, as defined in Table 3 of Danescu-Niculescu-Mizil et al. (2013, ACL) — "A computational approach to politeness with application to social factors."
- The paper's Table 3 gives strategy names, one example each, and effect sizes, but not the precise operational rules. The exact rules (word lists, dependency-parse patterns) were taken from the paper authors' own public implementation, `sudhof/politeness/features/politeness_strategies.py` (https://github.com/sudhof/politeness).
- `positive_lexicon` / `negative_lexicon` use the Liu & Hu (2005) Opinion Lexicon (public sentiment word lists). `hedge_wordlist` / `hedge_dependency` use the hedge-term list from Hyland (2005), as hard-coded in the original implementation (95 terms).
- `Hedges` was split into two versions: `hedge_wordlist` (any hedge term present anywhere in the request) and `hedge_dependency` (the hedge term must additionally be the governor of an `nsubj` dependency edge — i.e., a hedge *verb* with its own subject, e.g. "I **think** ..."). `hedge_dependency` is a strict subset of `hedge_wordlist` by construction, confirmed empirically (see Verification results below).
- Dependency parsing was done with spaCy (`en_core_web_sm`), not the Stanford Dependency Parser the original paper used. The two label sets partially differ — `nsubj`, `dobj`, and `det` map directly, but the original's collapsed `prep_by` / `prep_in` relations (used for `indirect_btw` and the "in fact" sub-case) don't exist in spaCy's scheme and were reconstructed as a two-hop check (`prep` token + its `pobj` child). See Known Limitations below.
- The original implementation's `Initial Polar` / `Aux Polar` were deliberately excluded — these are heuristics the original authors used elsewhere to help identify *whether a sentence is a request*, not politeness strategies in their own right, and are not part of Table 3.

### Feature columns

| Column | Type | Strategy |
|---|---|---|
| `gratitude` | bool | Thanking / appreciation ("I really **appreciate** ...") |
| `deference` | bool | Sentence-initial compliment ("**Nice work** ...") |
| `greeting` | bool | Sentence-initial greeting ("**Hey**, ...") |
| `positive_lexicon` | bool | Contains a word from the Liu positive-sentiment lexicon |
| `negative_lexicon` | bool | Contains a word from the Liu negative-sentiment lexicon |
| `apologizing` | bool | "Sorry" / "excuse me" / "I apologize" / "forgive me" |
| `please` | bool | "Please", not sentence-initial |
| `please_start` | bool | "Please", sentence-initial |
| `indirect_btw` | bool | "By the way ..." construction |
| `direct_question` | bool | Sentence starts (1st or 2nd word) with what/why/who/how |
| `direct_start` | bool | Sentence starts with so/then/and/but/or |
| `counterfactual_modal` | bool | Contains "could you" or "would you" |
| `indicative_modal` | bool | Contains "can you" or "will you" |
| `first_person_start` | bool | Sentence-initial I/my/mine/myself |
| `first_person_pl` | bool | Contains we/our/us/ourselves (any position) |
| `first_person` | bool | I/my/mine/myself, not sentence-initial |
| `second_person` | bool | you/your/yours/yourself, not sentence-initial |
| `second_person_start` | bool | Sentence-initial you/your/yours/yourself |
| `factuality` | bool | Contains really/actually/honestly/surely |
| `hedge_wordlist` | bool | Contains any term from the 95-term hedge list |
| `hedge_dependency` | bool | A hedge term governs an `nsubj` dependency edge |

### Verification results

- Ran on all 10,956 rows in 21.7 seconds, 0 errors (preceded by a 1,000-row test: 3.0s, 0 errors).
- Hit rates by source (% of rows where the feature is `True`) — shown against the paper's Table 3 "in top quartile" numbers for magnitude reference only. **These are different statistics** (ours: share of all rows using the strategy; the paper's: share of the strategy's users who land in the top politeness quartile), so they are not expected to match numerically — only to be in a plausible range of each other.

| Feature | Wikipedia | Stack Exchange | Paper (top-quartile ref.) |
|---|---|---|---|
| second_person | 65.0% | 67.3% | 30% |
| positive_lexicon | 44.8% | 36.0% | 32% |
| first_person | 40.4% | 19.6% | 28% |
| hedge_wordlist | 35.6% | 25.9% | 28% (paper: dependency version) |
| negative_lexicon | 33.3% | 31.2% | 22% |
| first_person_start | 28.7% | 14.9% | 29% |
| direct_question | 21.0% | 31.3% | 15% |
| hedge_dependency | 16.8% | 9.3% | 28% (paper) |
| counterfactual_modal | 9.6% | 7.4% | 52% |
| first_person_pl | 8.8% | 4.9% | 27% |
| direct_start | 8.8% | 10.8% | 9% |
| greeting | 8.5% | 0.7% | 45% |
| gratitude | 6.7% | 1.8% | 78% |
| indicative_modal | 6.5% | 10.1% | 27% |
| second_person_start | 5.7% | 5.7% | 17% |
| factuality | 4.6% | 5.1% | 13% |
| please | 3.7% | 6.7% | 57% |
| apologizing | 2.0% | 3.2% | 53% |
| deference | 1.4% | 0.9% | 70% |
| please_start | 0.8% | 2.2% | 22% |
| indirect_btw | 0.7% | 0.1% | 58% |

- `hedge_wordlist` vs. `hedge_dependency`: hit rates 29.8% vs. 12.2%. Overall agreement 82.5%. `hedge_dependency` is a **strict subset** of `hedge_wordlist` — every one of the 1,342 rows where `hedge_dependency` is `True` also has `hedge_wordlist` = `True` (0 exceptions), confirming the two implementations are logically consistent with each other.
- Correlation-sign check against the paper's Table 3 (Pearson correlation between each 0/1 feature and `Normalized Score`, computed separately by source; the paper's Table 3 itself was built on Wikipedia only): **21/21 features have a Wikipedia correlation sign matching the paper's Table 3.** Stack Exchange signs mostly agree too; the one near-exception is `first_person_pl` (Wikipedia +0.026, Stack Exchange −0.011), which is not a genuine sign conflict — both values are close to zero.

## Known Limitations

- **Politeness ≠ Indirectness.** This corpus is annotated for perceived politeness, not directness/indirectness. The two are correlated but not equivalent — this distinction matters if this dataset is later aligned with an indirectness-labeled task.
- **Domain gap.** The text comes from Wikipedia editor talk pages and StackExchange technical Q&A comments. Both are informal, public, task-oriented online communities — there is a register gap between this data and formal workplace written communication.
- **Backtick-code removal can leave incomplete-sounding sentences.** In Stack Exchange, deleting backtick-wrapped code spans entirely (rather than just unwrapping them) sometimes leaves a grammatically incomplete sentence, e.g. "What is the definition of ? Is it a local variable?" This does not affect the ability to read the remaining natural-language content, but it is a visible artifact of the cleaning rule.
- **Flag rates are low (~1–4%).** `is_too_short` and `is_high_disagreement` each mark roughly 1–4% of rows depending on source. Whether to filter on either flag is left to the modeling stage.
- **Some politeness-marker features are sparse.** Strategies like `gratitude`, `deference`, and `indirect_btw` fire on single-digit to low-teens percentages of rows, and are noticeably sparser on Stack Exchange than Wikipedia (e.g. `greeting`: 8.5% Wikipedia vs. 0.7% Stack Exchange). Downstream modeling that relies on these features should account for the resulting small sample sizes, particularly on Stack Exchange.
- **spaCy's dependency labels aren't identical to the original paper's Stanford Dependency Parser labels.** `nsubj`, `dobj`, and `det` map directly, but the collapsed `prep_by` / `prep_in` relations used by the original implementation don't exist in spaCy's scheme and were reconstructed as an adapted two-hop check. This is a faithful adaptation of the original rules' *intent*, not a line-by-line reimplementation of the original code.

## Version Info

- **Stage 1–3 (explore/clean/export) generated:** 2026-08-31
- **Stage 4–5 (feature engineering/export) generated:** 2026-08-31
- **Notebook:** `Data_Cleaning.ipynb`
- **Output files (two, both current — neither supersedes the other):**
  - `stanford_politeness_clean.csv` — 10,956 rows × 8 columns. Cleaned text + disagreement/short-text flags only, no politeness-marker features.
  - `stanford_politeness_features.csv` — 10,956 rows × 29 columns. Everything in `stanford_politeness_clean.csv`, plus the 21 boolean politeness-marker feature columns from Stage 4.
- **Final row count (both files):** 10,956
