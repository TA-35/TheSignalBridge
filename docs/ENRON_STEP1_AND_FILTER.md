# Enron Step 1 and the Shared Filter

This covers how the Enron source and gold files get built, and how to run the shared filter on the generated rewrites. It follows the Data Team How-To Guide for the final build.

You'll need Python 3.11 with the packages from the guide, plus `sentencepiece` and `protobuf` for the NLI model. Run everything from the repo root.

## Step 1: building the Enron files

The script is `Src/source/model/tone/enron_step1.py`. Each step saves its output in `data/step1/`, so you can stop and commit between steps.
python Src/source/model/tone/enron_step1.py clean # body only, 5-120 words, junk filter, exact dedupe, 10k pool
python Src/source/model/tone/enron_step1.py pii # swaps names and phone numbers for consistent fakes
python Src/source/model/tone/enron_step1.py piicheck # should report 0 real leaks
python Src/source/model/tone/enron_step1.py dedupe # removes near duplicates (MinHash 0.85)
python Src/source/model/tone/enron_step1.py signals # runs the tone, politeness and circa adapters
python Src/source/model/tone/enron_step1.py split # 60 gold plus 40 reserves first, then about 1,000 source
python Src/source/model/tone/enron_step1.py piicheck # checks the final gold and source files too
python Src/source/model/tone/enron_step1.py swapgold --drop enron_00003,enron_00008

### What each step does

clean keeps just the message body and cuts quoted replies, forwards and signatures. It keeps messages between 5 and 120 words and drops automated mail plus junk: spam, leftover forwarded headers, emails that are only a signature, and trading or data lines. Exact copies are removed by hashing the text, and then it samples a working pool of 10,000. It also builds the list of real employee names that the PII step uses.

pii swaps names and phone numbers for fake ones through one shared mapping, so the same person always gets the same fake name. Presidio alone missed a lot of Enron names, so on top of it the script catches routing names like Name/HOU/ECT@ECT and Name@ENRON, "Last, First", known employee names, and names that are also normal words (Dawn, Frank, Bill) when they're clearly used as a name. It keeps line breaks and spacing, leaves place names like "Robert's Bay" alone, and never uses a real Enron name or an everyday word as a fake.

piicheck compares every scrubbed message with its original and lists any real name or phone number still sitting there.

dedupe removes emails that are nearly identical (MinHash, 128 permutations, Jaccard 0.85).

signals runs the same adapters the live pipeline uses and keeps only model, label and confidence. If an adapter fails, the record says `label: "unknown", confidence: 0.0`, which is what production does.

split uses `random.seed(42)` to set aside 60 gold messages (45 flagged, 15 clear) plus 40 reserves. It removes those and anything close to them from the pool, then picks 850 flagged and 150 clear messages for the source file.

swapgold replaces any gold message you reject by hand with a reserve of the same kind, flagged or clear.

### When a message counts as flagged

A message needs a rewrite if politeness is low or high, circa says indirect, or it has a hedge phrase like "if you get a chance", "just wondering", "circle back", "might be worth" or "no rush but".

### Checking the gold by hand

After split, read every message in `data/step1/gold_review.csv`. Note the ids of anything that isn't a real message between colleagues (spam, headers, signatures, data lines) or where the scrub made the text read oddly, and run swapgold with those ids.

### What gets committed

| File | What's in it | In git? |
|---|---|---|
| `data/gold/enron_gold.jsonl` | the 60 gold messages | yes |
| `data/source/enron_source.jsonl` | about 1,000 source messages | yes |
| `data/step1/counts.json` | the counts for the team chat | yes |
| `data/step1/known_names.json` | real employee names | never |
| `data/step1/1_clean.csv` | text from before the scrub | never |
| everything else in `data/step1/` | working files | no |

## The shared filter (day 2)

The script is `Src/source/data_prep/filter_pairs.py`. It reads every `data/generated/*_gen.jsonl` and puts each pair through these checks in order. A pair is rejected at the first one it fails.

| # | Check | Rejected when |
|---|---|---|
| 0 | gold_overlap | the source is a gold message or very close to one |
| 1 | json_valid | rewrite, notes or meaning is missing |
| 2 | notes_ok | there aren't 1 to 3 notes, or a note is 20 words or longer |
| 3 | dropped_entity | a name, organisation, date, time, money amount or number from the source isn't in the rewrite |
| 4 | added_entity | the rewrite has one that wasn't in the source |
| 5 | length | the rewrite isn't between 0.5 and 2.5 times the source length |
| 6 | contradiction | `cross-encoder/nli-deberta-v3-base` says the rewrite contradicts the source |

Entities are compared in lowercase, and short forms like "Thurs" count as "Thursday", which the guide warned would otherwise cause false rejections. The gold check compares against every gold message. Something counts as a near copy if its character 5-grams overlap at least 50% (Jaccard), or if at least 80% of a gold message shows up inside a longer email.
python Src/source/data_prep/filter_pairs.py goldcheck # source rows that look like gold, should be 0
python Src/source/data_prep/filter_pairs.py fake --n 80 # makes test pairs in data/test_generated/
python Src/source/data_prep/filter_pairs.py filter --test # test run, writes to data/test_filtered/
python Src/source/data_prep/filter_pairs.py filter # the real run
python Src/source/data_prep/filter_pairs.py spotcheck # 10% sample split three ways

The real run writes to `data/filtered/`: `train.jsonl`, `rejects.jsonl` with the reason for each rejection, and `filter_report.json` with the rejection rate for each check. If one check rejects more than 30%, it gets flagged, and that usually means the prompt needs fixing rather than the filter. The real run also refuses to start if there are test files in `data/generated/`.

To run the tests: `python -m pytest Src/source/data_prep/tests -q`
