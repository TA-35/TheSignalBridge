# Data Card: Enron Email Dataset (Cleaned Subset)

## Source

- **Dataset:** Enron Email Dataset, May 7, 2015 Version
- **Original source:** https://www.cs.cmu.edu/~enron/ (CMU-hosted release)
- **License:** Non-commercial research use only
- **Original size:** 517,401 email files across ~150 employee mailboxes (`maildir/` structure), ~1.82 GB uncompressed
- **Downloaded:** 2026-08-30

I went in expecting this to be more "apply a known recipe" than it turned out to be.
Circa and Stanford Politeness are corpora someone else already shaped into a clean
question/request format — this is 500k+ raw email files with no such structure, so most
of the real work was figuring out what was actually wrong before deciding how to fix it.

I'm writing this the way I actually worked through it — what I expected, what I found,
and where I paused to check something before trusting it — rather than as a tidy list
written after the fact.

## Stage 1 — Ingest & parse

**Plan:** walk the `maildir/<person>/<folder>/<file>` tree and parse each file as a
standard RFC-822 email, splitting the header block (From, To, Cc, Subject, Date,
Message-ID, In-Reply-To, References) from the body.

The folder depth wasn't consistent going in — some files sit directly under a person's
mailbox with no subfolder at all, others are nested several levels deep — so the walk
needed to handle both, not assume a fixed structure.

Ran against the full corpus: 517,401 files, 0 parse errors.

**Bug found here:** files with no subfolder (e.g. `campbell-l/1`, not `campbell-l/sent/1`)
were getting their filename duplicated into the `folder` column too. A parse can report
"0 errors" and still put the wrong thing in a column — I only caught this by actually
looking at a row of output, not by trusting the error count. Fixed and re-verified against
both the no-subfolder and nested-subfolder cases before moving on.

## Stage 2 — Clean

This stage produced most of the real findings, and every one of them came from checking
actual output text, not from the summary numbers looking clean.

**Deduplication.** Checked using Message-ID, falling back to a sender+date+subject+body
hash for the handful of emails missing one.

**Result: zero duplicates**, across all 517,401 rows.

This one genuinely surprised me. Enron's mailbox structure is well known for heavy
duplication — the same email in the sender's Sent folder and again in every recipient's
Inbox — and that assumption is even written into our own team's roadmap doc. I expected
dedup to remove a meaningful chunk of the corpus. It removed nothing. Because the result
contradicted a documented assumption, I checked it twice before writing it down as fact —
first within a single person's mailbox, then again across the full dataset. Best guess:
this specific CMU-hosted release has already been de-duplicated upstream, before it ever
reached me. I couldn't find that documented anywhere, so I'm stating it as my inference,
not a confirmed fact.

**Stripped quoted reply history** — cut anything following `-----Original Message-----`
markers or `"On <date>, X wrote:"` patterns, and removed manually-quoted lines (`>`-prefixed).

**Stripped forwarded-message markers.** Enron's client marks forwards with
`"----- Forwarded by X on <date> -----"`. My first regex for this ran fine and looked
correct, but when I re-checked how many rows still contained "Forwarded by" afterward, the
number was 74,112 — barely moved. The fix had silently failed. The cause: Python's `.`
doesn't match a newline by default, and this marker's date/time routinely wraps onto a
second line (`"...on 05/31/2001 04:18\nPM..."`), which is exactly where my pattern broke.
Adding `re.DOTALL` fixed it — residual count dropped to 206. I only found this because I
checked the *effect* of the fix rather than assuming a clean run meant a correct one.

**Removed automated/bulk mail.** Sender/subject pattern matching (mailer-daemon,
postmaster, no-reply, undeliverable, out-of-office) caught 2,295 rows on the first pass.
Later, while trying to understand why some "threads" turned out to be hundreds of
near-identical messages, I found two more automated sources the pattern list had missed:
`CALENDAR ENTRY:` scheduling exports, and a recurring internal alert —
`"HourAhead schedule download failed"` — sent from an address with no obvious automated
signature. Adding both brought total removal to 5,778 rows.

**Normalized encoding** — fixed quoted-printable artifacts (soft line breaks, `=XX` hex
codes) and stripped stray HTML, deliberately light-touch to avoid corrupting text that was
already fine.

**Masked PII.** Emails and phone numbers matched and redacted by regex; sender/recipient
fields replaced with consistent `Person_N` pseudonyms. Being upfront about the gap: a
first name mentioned casually in the body or subject ("dinner with Louise and John")
passes straight through — regex can't reliably detect names. I confirmed this by
spot-checking a cleaned row and seeing a real name still sitting in the subject line, not
by assuming the limitation existed.

**Filtered by length and language** — dropped bodies under 10 characters or over 20,000,
plus a rough ASCII-ratio check for obvious non-English outliers. Heuristic, not a real
language classifier.

## Stage 3 — Wrangle into schema

Reshaped cleaned rows into the team's ERD-defined `MESSAGE` and `EMAIL_META` tables.

`raw_text` and `cleaned_text` are genuinely separate values — the original body is
captured before cleaning touches it. They weren't, at first: an earlier version of
`clean_enron.py` only kept the post-cleaning text, so both columns ended up identical,
which quietly defeats the point of having two. Fixed by having the cleaning stage carry
the pre-cleaning body through as its own field.

**Thread reconstruction was the biggest surprise in the whole pipeline.** The plan was
always to link replies via `In-Reply-To` and `References` — the standard, reliable
approach. Checking directly whether that was actually possible here: both headers are
**0% populated**, across every row. Not rare — entirely absent. Header-based threading
isn't an option with this corpus, full stop.

The fallback groups by normalised subject (Re:/Fw:/Fwd: stripped) plus sender, inside a
7-day window, so two unrelated emails sharing a generic subject like "Meeting" don't get
merged just because the words match. This took two failed attempts to get right: the
first tried building a proper reply-chain walker despite the headers being empty
(pointless — nothing to walk), and the second had a real bug where the fallback almost
never actually triggered. Both were caught by checking the resulting thread count
directly — 496,679 threads for 496,679 messages was an obvious tell that nothing had
actually been grouped.

## Stage 4 — Sample

Drew a stratified, reproducible sample (fixed random seed) for the annotation set:
stratified by message length (short/medium/long) and a rough ambiguity heuristic
(question marks, hedging language, very short text), capped at 2 messages per thread so
one long back-and-forth doesn't dominate the sample.

## Schema

| Column | Table | Type | Description |
|---|---|---|---|
| `message_id` | MESSAGE | string (uuid) | Generated ID — not the same as Enron's own Message-ID header |
| `source_dataset_id` | MESSAGE | string | `"enron"` |
| `raw_text` | MESSAGE | string | Body exactly as parsed, before any cleaning |
| `cleaned_text` | MESSAGE | string | Body after quoted-history/signature/forward stripping, encoding fixes, PII masking |
| `char_count` | MESSAGE | int | Length of `cleaned_text` |
| `external_ref` | MESSAGE | string | Original file path, e.g. `maildir/campbell-l/sent/12` |
| `thread_id` | MESSAGE | string | Subject+sender+time-window grouping (see Known Limitations) |
| `sender` | EMAIL_META | string | Pseudonymised (`Person_N`) |
| `recipients` | EMAIL_META | string | Pseudonymised, comma-separated |
| `cc` | EMAIL_META | string | Pseudonymised, comma-separated |
| `subject` | EMAIL_META | string | Original subject line (not pseudonymised — may contain names) |
| `sent_at` | EMAIL_META | string | Original RFC-822 date string |

## Verification Results

| Stage | Rows in | Rows out | Removed |
|---|---|---|---|
| Parse | 517,401 files | 517,401 rows | 0 (0 parse errors) |
| Dedup | 517,401 | 517,401 | 0 (verified twice, not assumed) |
| Automated/bulk removal | 517,401 | 511,623 | 5,778 |
| Length/language filter | 511,623 | 455,514 | 56,109 |
| **Final cleaned rows** | | **455,514** | |

- `"Forwarded by"` residue: 206 rows after the DOTALL fix, down from 74,112 with the buggy
  regex.
- Threads: 196,286 distinct groups across 455,514 messages (~2.4 messages/thread average).
- Annotation sample: 400 messages, 279 unique senders, fixed seed for reproducibility.

## Known Limitations

- **The zero-duplication finding is specific to this exact release.** Don't assume it
  holds for a different Enron distribution (e.g. the original FERC release) without
  re-checking — I'm flagging this explicitly because it contradicts the commonly-cited
  assumption about this dataset.
- **PII masking doesn't catch names in free text** — only structured PII (emails, phone
  numbers, header addresses) is masked.
- **Thread grouping is a proxy, not real reply-chain threading.** Will miss a reply that
  changed its subject line, and could occasionally over-merge two unrelated messages from
  the same sender inside the same 7-day window if the subjects happen to match.
- **Length/language filtering is heuristic**, not a real language-detection model.
- **206 rows of "Forwarded by" residue remain** — not yet traced to a specific cause,
  logged as an open item rather than assumed fixed.

## Version Info

- **Pipeline stages generated:** 2026-08-30
- **Scripts:** `Src/source/ingest/parse_enron.py`, `Src/source/clean/clean_enron.py`, `Src/source/wrangle/build_message_table.py`, `Src/source/annotate/sample_annotation_set.py`
- **Output files (gitignored — regenerate locally per `data/README.md`):**
  - `data/staging/enron_parsed.csv` — 517,401 rows
  - `data/staging/enron_cleaned.csv` — 455,514 rows
  - `data/staging/message_enron.csv`, `email_meta_enron.csv` — 455,514 rows each
  - `data/staging/annotation_sample_v1.csv` — 400 rows, seed-locked
- **Final row count:** 455,514
