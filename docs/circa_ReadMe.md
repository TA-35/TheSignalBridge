# Circa Dataset

## What this is

Circa is a public dataset of indirect answers to yes/no questions. Each row has a short scenario, a question, an answer that does not say yes or no directly, and a label saying what the answer actually meant. In our project we use Circa as a probe. It helps us test whether our system can notice when an answer is indirect. We do not train on it.

This document explains how we took the raw Circa file and turned it into clean, ready to use data. The work happens in three scripts, each doing one job, so the stages stay separate and easy to follow.

## The three stages

### 1. Ingestion and profiling (`parse_circa.py`)

This script loads the raw file and studies it without changing anything. The goal is to understand the data before we touch it. It reports the size, the columns, missing values, duplicates, text lengths, and the balance of the labels.

What we found:

* The file has 34,268 rows and 8 columns.
* The columns that matter to us are `question-X` (the question), `answer-Y` (the indirect answer), and `goldstandard1` and `goldstandard2` (the labels saying what the answer meant).
* About 8 percent of the gold labels are blank (2,743 rows). These are cases where the human annotators could not agree on a meaning, so they are genuinely ambiguous.
* There are 197 repeated question and answer pairs.
* When we count a clear yes or no as a direct answer and leave out the blank labels, the split of direct to indirect comes out around 80 to 20.

### 2. Cleaning (`clean_circa.py`)

This script takes the raw file and fixes it. Every step prints a count before and after, so the changes are easy to audit.

What it does:

* Removes any fully identical rows, as a safety check.
* Removes the 197 repeated question and answer pairs, keeping the first of each.
* Drops the rows with a blank gold label, since without a label they cannot serve as a reliable reference. We keep the indirect answers themselves. Only the unlabelled rows go.
* Strips extra spaces from the text fields.
* Drops any row that ends up empty after stripping.

Result: the data goes from 34,268 rows down to 31,340 clean rows, saved as `circa_clean.parquet`.

### 3. Wrangling (`circa_wrangle.py`)

This script reshapes the cleaned data into our shared MESSAGE format, so Circa looks the same as every other dataset we add later. It also checks its own output before saving.

What it does:

* Maps each Circa answer into our standard columns: a unique reference, a source tag, the raw text, the cleaned text, the character count, and the collection time. The answer is treated as the message, because the answer is the thing whose meaning we decode.
* Keeps the question and the gold label in a separate file, `circa_eval.parquet`, because they are the answer key for testing, not message text.
* Validates the result before saving. It checks the columns, the data types, that no required field is empty, that the character count matches the text, and that every id is unique. If any check fails, the script stops instead of saving bad data.

Result: two files land in `data/staging/`. The file `message_table.parquet` holds the 31,340 messages in the shared format, and `circa_eval.parquet` holds the matching answer key.

## How to run it

Run these from the repo root, with the virtual environment active.

```
python Src/source/ingest/parse_circa.py
python Src/source/clean/clean_circa.py
python Src/source/wrangle/circa_wrangle.py
```

## A note on the data files

The raw and cleaned data are not stored in this repository. Our ignore rules keep everything under `data/raw` and `data/staging` out of version control, so licensed data never gets committed. To reproduce the outputs, download the raw Circa file into `data/raw` and run the scripts above. They recreate the same results on your own machine.

## Decisions worth knowing

* We chose `goldstandard1` as the primary label. It agrees with `goldstandard2` on about 92 percent of the doubly labelled rows, so the choice moves very little.
* We defined a direct answer as a clear yes or no with the blank labels excluded. This is what gives the 80 to 20 split. A different definition gives a different number, so we always state the definition alongside the figure.
* We removed the unlabelled rows to get a clean reference set. It is worth remembering that those were the most ambiguous answers, so they are set aside rather than solved. If a later stage wants to study ambiguity itself, that is where to look.
