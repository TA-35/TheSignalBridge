# Data Directory

This folder holds the data pipeline's working files. Contents are
mostly gitignored on purpose - the actual data (parsed/cleaned Enron
emails, Circa data, etc.) contains information that shouldn't sit in
GitHub, either because it's large, or because it's derived from real
people's private email before PII masking is applied.

## Structure

- **raw/** — untouched downloads exactly as pulled from the source
  (e.g. the Enron maildir tarball, unpacked). Never edited. Gitignored.
- **staging/** — intermediate pipeline outputs: parsed CSVs, cleaned
  CSVs, wrangled MESSAGE/EMAIL_META tables, the locked annotation
  sample. Gitignored, since these still contain unmasked or
  near-final message text.
- **processed/** — reserved for final, ready-to-load outputs (e.g.
  the version that would actually get loaded into the database).
  Not yet populated.

## Reproducing the data

Since none of the actual data files are committed, anyone who needs
them has to regenerate them locally by running the pipeline scripts
in order:

1. Download the Enron dataset into `raw/enron/` (see
   `docs/SOURCE_DATASET.md` for the source URL and license)
2. `python3 Src/source/ingest/parse_enron.py`
3. `python3 Src/source/clean/clean_enron.py`
4. `python3 Src/source/wrangle/build_message_table.py`
5. `python3 Src/source/annotate/sample_annotation_set.py`

Each script's output and expected row counts are documented in
`docs/SOURCE_DATASET.md`.