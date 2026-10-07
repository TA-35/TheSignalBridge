"""
stanford_step1.py
Step 1 of the final build guide for the Stanford Politeness Corpus: turn the
cleaned corpus into
  data/gold/stanford_gold.jsonl      (60 messages, human-checked, never touched again)
  data/source/stanford_source.jsonl  (1,000 messages with signals)
  data/step1/stanford/               (reserves, counts, id map, working files)

Same recipe as Src/source/model/tone/enron_step1.py, with the Stanford-specific
parts from Sanket's review of the first Stanford push:
  - sample only from the politeness model's validation + test splits
    (grouped_split(rows, seed=5120) from train_politeness_nn.py), so the
    politeness signal is never in-sample
  - "<url>" tokens and raw URLs become "[URL]" (the filter keeps [A-Z_]+ tags)
  - @Handles, "User:Name" and PERSON names go through ONE real -> fake mapping
    shared by gold, reserves and source
  - signals come from the three frozen pipeline adapters via
    compose_prompt.clean_signals; hand labels never go in these records
  - rows where the politeness adapter warns "no_english_words" or
    "mostly_unknown_words" are dropped

Run from the repo root, one step at a time:

  python Src/source/model/politeness/stanford_step1.py clean      # val+test only, [URL], 5-120 words, exact dedupe
  python Src/source/model/politeness/stanford_step1.py pii        # handles + User: + PERSON -> consistent fakes
  python Src/source/model/politeness/stanford_step1.py piicheck   # should report 0 leaks; lists the handle rows to eyeball
  python Src/source/model/politeness/stanford_step1.py dedupe     # near duplicates with MinHash (0.85)
  python Src/source/model/politeness/stanford_step1.py signals    # run the three pipeline adapters (resumes if stopped)
  python Src/source/model/politeness/stanford_step1.py split      # 60 gold + 40 reserves first, then 1,000 source
  python Src/source/model/politeness/stanford_step1.py check      # the pre-push self-check
  python Src/source/model/politeness/stanford_step1.py swapgold --drop stanford_00003,stanford_00008

Flagged = politeness low OR high, circa indirect, or a hedge phrase (identical to Enron).
"""

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent

CORPUS = Path("data/Stanford_Politeness/stanford_politeness_clean.csv")
WORK = Path("data/step1/stanford")          # NOT data/step1/ - Enron's step 1 writes there
GOLD_OUT = Path("data/gold/stanford_gold.jsonl")
SOURCE_OUT = Path("data/source/stanford_source.jsonl")
RESERVE_OUT = WORK / "gold_reserve.jsonl"
GOLD_REVIEW = WORK / "gold_review.csv"
COUNTS_OUT = WORK / "counts.json"
IDMAP_OUT = WORK / "id_map.json"
PII_LOG = WORK / "2_pii_log.csv"

# ---- copied verbatim from Src/source/model/tone/enron_step1.py (PR #13,
# branch feature/enron-final-data, file last changed in commit 9a1c9c5).
# Must stay identical to Enron's.
# flagged = needs a rewrite. Per the plan: politeness low OR high (over-polite
# is just as unclear), circa indirect, or a hedge phrase anywhere in the text
FLAG_RULES = {"politeness": {"low", "high"}, "circa": {"indirect"}}
HEDGES = re.compile(
    r"if you get a chance|when you get a chance|if you have a (?:minute|moment|sec)|when you have a (?:minute|moment|sec)"
    r"|just (?:wondering|checking|curious|a thought|a heads up)|i was wondering|wondering if"
    r"|circle back|touch base|might be worth|may be worth|could be worth|worth a look"
    r"|no rush,? but|no pressure,? but|not urgent,? but|whenever you can|at your convenience"
    r"|would be (?:great|nice|good) if|it might be (?:good|nice|helpful)|you (?:may|might) want to"
    r"|perhaps we could|maybe we could|not sure if|if (?:possible|you can|you could)|could you possibly",
    re.I)
SEED = 42
N_GOLD_FLAGGED, N_GOLD_CLEAR = 45, 15
N_RES_FLAGGED, N_RES_CLEAR = 30, 10
N_SRC_FLAGGED, N_SRC_CLEAR = 850, 150
# ---- end of the verbatim block

SPLIT_SEED = 5120                     # the seed the politeness model was trained with
SPLITS_USED = ("validation", "test")  # never "train": those rows are in-sample
MIN_WORDS, MAX_WORDS = 5, 120
GOLD_START, RESERVE_START, SOURCE_START = 1, 101, 1001
DROP_WARNINGS = {"no_english_words", "mostly_unknown_words"}
URL_TAG = "[URL]"


# ---------------------------------------------------------------- helpers
def norm_hash(t):
    t = re.sub(r"[^\w\s]", "", str(t).lower())
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()


def wc(t):
    return len(str(t).split())


def save_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def update_counts(**kw):
    WORK.mkdir(parents=True, exist_ok=True)
    c = json.load(open(COUNTS_OUT)) if COUNTS_OUT.exists() else {}
    c.update(kw)
    json.dump(c, open(COUNTS_OUT, "w"), indent=2)


# ---------------------------------------------------------------- 1. clean
# "<url>" / "<link>" are the corpus' own placeholders; the rest are real links
LINK = re.compile(
    r"<url>|<link>"
    r"|(?:https?://|www\.)[^\s<>\"']*[^\s<>\"'.,;:!?)\]]"
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|edu|gov)\b(?:/[^\s<>\"']*[^\s<>\"'.,;:!?)\]])?",
    re.I)
# other corpus placeholders / leftover markup (<person>, <tt>, <s> ...): the
# message is missing a piece, so it is dropped rather than patched
PLACEHOLDER = re.compile(r"</?[a-zA-Z_]+>")


def normalise_links(t):
    return LINK.sub(URL_TAG, str(t))


def step_clean(a):
    sys.path.insert(0, str(HERE))
    from train_politeness_nn import grouped_split, load_rows   # the exact split the model used

    rows = load_rows(CORPUS)
    splits = grouped_split(rows, SPLIT_SEED)
    split_of = {int(i): name for name, idx in splits.items() for i in idx}
    start = len(rows)

    df = pd.DataFrame([{"row": i, "corpus_id": r["Id"], "site": r["source"],
                        "community": r["Community"], "split": split_of[i],
                        "body": r["Request"]} for i, r in enumerate(rows)])
    df = df[df["split"].isin(SPLITS_USED)]
    after_split = len(df)

    df["body"] = df["body"].map(normalise_links)
    links = int(df["body"].str.count(re.escape(URL_TAG)).sum())

    has_placeholder = df["body"].str.contains(PLACEHOLDER)
    df = df[~has_placeholder]
    after_placeholder = len(df)

    df = df[df["body"].map(wc).between(MIN_WORDS, MAX_WORDS)]
    after_len = len(df)

    df["h"] = df["body"].map(norm_hash)
    df = df.drop_duplicates("h").drop_duplicates("corpus_id").drop(columns=["h"])

    WORK.mkdir(parents=True, exist_ok=True)
    df.to_csv(WORK / "1_clean.csv", index=False)
    print(f"corpus {start:,} -> validation+test {after_split:,} -> no placeholder tokens {after_placeholder:,} "
          f"-> {MIN_WORDS}-{MAX_WORDS} words {after_len:,} -> exact dedupe {len(df):,}")
    print(f"links normalised to {URL_TAG}: {links:,}")
    update_counts(corpus=start, split_seed=SPLIT_SEED, splits_used=list(SPLITS_USED),
                  after_split=after_split, after_placeholder_drop=after_placeholder,
                  after_length=after_len, after_exact_dedupe=len(df),
                  links_normalised=links,
                  flag_rule_copied_from="Src/source/model/tone/enron_step1.py @ 9a1c9c5 (feature/enron-final-data, PR #13)")


# ---------------------------------------------------------------- 2. PII
# words the NER tags as PERSON on Wikipedia / Stack Exchange text that are not
# people here: places, weekdays, greetings, and tech / product / maths names
NOT_PEOPLE = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "thanks", "regards", "cheers", "hi", "hello", "dear",
    "hey", "sorry", "please", "okay", "ok", "yes", "no", "wow", "hmm", "lol", "btw",
    "wikipedia", "wiki", "wiktionary", "commons", "google", "stack", "overflow", "stackoverflow",
    "exchange", "github", "amazon", "microsoft", "apple", "linux", "ubuntu", "debian", "windows",
    "mac", "java", "javascript", "jquery", "python", "perl", "ruby", "rails", "php", "sql",
    "mysql", "oracle", "html", "css", "xml", "json", "ajax", "regex", "bash", "git", "vim",
    "emacs", "eclipse", "xcode", "android", "iphone", "ipad", "ios", "nikon", "canon", "sigma",
    "firefox", "chrome", "safari", "drupal", "wordpress", "django", "flask", "latex", "tex",
    "matlab", "excel", "word", "outlook", "skype", "twitter", "facebook", "youtube", "imdb",
    "url", "user", "admin", "bot", "twinkle", "huggle", "afd", "fac", "rfc", "rfa", "dyk",
    "agent", "studio", "wifi", "wine", "mach", "germanic", "lutheran", "deuteronomy", "cyrillic",
    "mongolian", "antarctica", "antractica", "internet", "web", "api", "unicode", "ascii",
    "whatcha", "noooo", "kilo", "aardvarks", "yellow", "mazda", "wikilinks", "doubleclick",
    "mootools", "firebug", "jailbroken", "snow", "leopard", "banshee", "magix", "xoctave",
    "algorithm", "thunder", "whales", "rounds", "siam", "sharjah", "ladakh", "judaica", "quel",
    "cunard", "mazahua", "lofi", "stroke", "howdy",
}
# openers that look like a name before a comma ("Hmmm, ...", "Oops, ...")
INTERJECTION = re.compile(
    r"^(?:u+m+|u+h+|o+h+|a+h+|o+ps|w?h?oo+ps|h+m+n?|ye+a*h*|ya+|ye+p|yu+p|na+h|no+pe|u+gh|he+h|a+ha+|hu+h|"
    r"je+z|ge+z|wo+w|we+ll+|o+k(?:ay)?|alright|alrighty|congrat(?:s|ulations)|apolog(?:y|ies)|greetings|"
    r"corrections?|firstly|first|secondly|second|thirdly|third|lastly|finally|furthermore|moreover|however|"
    r"evidently|ordinarily|unfortun\w+|fortunately|honestly|seriously|actually|basically|personally|"
    r"interesting(?:ly)?|agreed|true|right|wrong|nice|cool|great|good|sure|done|fixed|thanks|thank|cheers|"
    r"sorry|please|update|edit|note|question|answer|comment|example|ps|pps|nb|fyi|imo|imho|afaik|btw)$", re.I)
# first names Faker can produce that read as something else in a sentence
FAKE_AVOID = {"jesus", "christ", "christian", "angel", "destiny", "precious", "mohammed", "muhammad",
              "summer", "autumn", "sky", "king", "prince", "princess", "duke", "earl", "baron"}
# everyday words that are also names - never replaced on their own
AMBIGUOUS = {
    "mark", "bill", "will", "may", "june", "april", "grant", "rich", "joy", "pat", "sue", "art",
    "don", "guy", "ray", "frank", "chuck", "dawn", "faith", "hope", "rose", "holly", "ivy",
    "iris", "amber", "price", "young", "white", "brown", "black", "green", "hall", "king",
    "long", "ward", "day", "rice", "bass", "fox", "hunt", "ross", "lane", "rock",
    "case", "small", "best", "hill", "stone", "wood", "cash", "bond", "gold",
    "major", "love", "west", "north", "south", "east", "dean", "baker", "cook",
}
# words that follow "@" but address nobody in particular
GENERIC_AT = {"everyone", "all", "op", "anyone", "downvoter", "downvoters", "mods", "moderators", "people"}
GREETING_STOP = {"there", "all", "again", "everyone", "guys", "folks", "both", "i", "im", "we", "you",
                 "it", "the", "this", "that", "so", "but", "and", "for", "to", "not", "no", "yes"}

# "@left = (...)" / "@array[0]" / "@interface" is code, not a handle
CODE_AT = re.compile(r"@\w+\s*(?:=|\[|\(|\{|;|\))|[\"'(\[{=]\s*@\w|@(?:interface|property|implementation|end|synthesize|"
                     r"media|import|override|param|return|selector|autoreleasepool)\b"
                     r"|@(?:arr|array|list|data|files?|rows?|items?|values?|args?|left|right|result|results|"
                     r"lines?|names?|keys?|INC|ARGV|ISA)\w*\b|@[A-Z0-9]+_[A-Z0-9_]+\b|@_\w*")
USER_COLON = re.compile(r"\bUser:\s?([A-Za-z0-9][\w.\-]*(?:\s[A-Z][\w.\-]*)?)")
USER_SPACE = re.compile(r"\b([Uu]ser)\s+([A-Z][\w\-]*[A-Za-z0-9])\b")
# two- and three-word handles: "@luser droog:", "@Thomas P:", "@Mark Trapp,", "@Kyle Cronin -"
AT_MULTI_COLON = re.compile(r"@([\w.'\-]+(?:[ ][\w.'\-]+){1,2})(?=\s?:)")
AT_CAP_PAIR = re.compile(r"@([A-Z][\w.'\-]*[ ][A-Z][\w.'\-]*)(?=\s?(?:,|-|–|—))")
# "@Derek Beattie I checked": no punctuation after it, so the second word only
# counts when it is not an ordinary word (decided in scrub with the corpus word list)
AT_CAP_LOOSE = re.compile(r"@([A-Z][\w.'\-]*)[ ]([A-Z][\w'\-]{2,})(?=\s)")
AT_USER_UNKNOWN = re.compile(r"@user unknown\b")      # Stack Exchange's name for a deleted account
AT_SINGLE = re.compile(r"(?<![\w.])@([A-Za-z0-9_](?:[\w.\-]*\w)?)")
GREETING = re.compile(r"(?:^|(?<=[.!?]\s))((?:Hi|Hey|Hello|Dear|Thanks|Thank you|Welcome)[, ]+)"
                      r"([A-Z][\w.]*(?:-\w+)*)")
LEADING = re.compile(r"^([\"'“]?)([A-Za-z][\w]*(?:-\w+)*)(?=\s?[:,]\s|\s-\s|-[A-Z])")


def common_words(texts, min_lower=2):
    """Words used in lowercase ("okay", "sorry", "example") are ordinary words,
    so a capitalised one at the start of a message isn't a name. Counted over
    the whole corpus, not just the sampled splits, so the list is stable."""
    lower = Counter()
    for t in texts:
        for w in re.findall(r"\b[a-z][a-z'\-]+\b", str(t)):
            lower[w] += 1
    return {w for w, c in lower.items() if c >= min_lower}


def step_pii(a):
    from faker import Faker
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    import spacy

    nlp_engine = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]}).create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    spacy_nlp = spacy.load("en_core_web_sm")

    df = pd.read_csv(WORK / "1_clean.csv")
    texts = df["body"].astype(str).tolist()
    with open(CORPUS, newline="", encoding="utf-8") as fh:
        common = common_words(r["Request"] for r in csv.DictReader(fh))
    common |= {"i", "i'm", "i'd", "i've", "i'll"}
    # fakes must never be a name or handle that is really in the corpus
    real_words = {w.lower() for t in texts for w in re.findall(r"[A-Za-z][\w'\-]*", t)}

    fake = Faker(); Faker.seed(SEED)
    mapping, fakes_made = {}, set()

    def fake_word(word, slot):
        """one shared dictionary: the same real name / handle always gets the same fake"""
        core = word.strip(".,;:!?")
        poss = ""
        if core.lower().endswith("'s"):
            core, poss = core[:-2], "'s"
        if not core:
            return word
        key = (slot, core.lower())
        if key not in mapping:
            gen = fake.first_name if slot == "FIRST" else fake.last_name
            avoid = real_words | AMBIGUOUS | NOT_PEOPLE | FAKE_AVOID
            cand = gen()
            for _ in range(300):
                if cand.lower() not in avoid and cand not in fakes_made:
                    break
                cand = gen()
            else:
                cand = cand + "son"
            mapping[key] = cand
            fakes_made.add(cand)
        return word.replace(core + poss, mapping[key] + poss, 1)

    def fake_person(span):
        """keeps the original spacing, only swaps the words themselves"""
        parts = re.split(r"(\s+)", span)
        words = [i for i, p in enumerate(parts) if p and not p.isspace()]
        for n, i in enumerate(words):
            parts[i] = fake_word(parts[i], "FIRST" if n == 0 else "LAST")
        return "".join(parts)

    found = Counter()
    log = []

    def scrub(row, text):
        t = text

        def swap(kind, real, keep_before=""):
            new = fake_person(real)
            found.update([kind])
            log.append({"row": row, "kind": kind, "real": real, "fake": new})
            return keep_before + new

        # 1) "User:Dr Joe" -> fake name, "user CBERLET" -> "user <fake>"
        t = USER_COLON.sub(lambda m: swap("USER", m.group(1)), t)
        t = USER_SPACE.sub(lambda m: m.group(0) if m.group(2).lower() in common | NOT_PEOPLE
                           else swap("USER", m.group(2), m.group(1) + " "), t)

        # 2) @handles, longest form first; the "@" goes too
        t = AT_USER_UNKNOWN.sub(lambda m: swap("HANDLE", "user unknown"), t)
        t = AT_MULTI_COLON.sub(lambda m: swap("HANDLE", m.group(1)), t)
        t = AT_CAP_PAIR.sub(lambda m: m.group(0) if m.group(1).split()[1].lower() in common | NOT_PEOPLE
                            or INTERJECTION.match(m.group(1).split()[1])
                            else swap("HANDLE", m.group(1)), t)
        t = AT_CAP_LOOSE.sub(lambda m: m.group(0) if m.group(2).lower() in common | NOT_PEOPLE
                             or INTERJECTION.match(m.group(2))
                             else swap("HANDLE", m.group(1) + " " + m.group(2)), t)
        t = AT_SINGLE.sub(lambda m: m.group(1) if m.group(1).lower() in GENERIC_AT
                          else swap("HANDLE", m.group(1)), t)

        # 3) names used as a greeting or to open the message: "Hi Sukh -", "Rklawton, I ..."
        def greet(m):
            if m.group(2).lower() in GREETING_STOP | NOT_PEOPLE or m.group(2) in fakes_made:
                return m.group(0)
            return swap("GREETING", m.group(2), m.group(1))
        t = GREETING.sub(greet, t)

        def lead(m):
            w = m.group(2)
            if (len(w) < 3 or w in fakes_made or w.lower() in common | NOT_PEOPLE | AMBIGUOUS
                    or INTERJECTION.match(w) or (w.isupper() and len(w) <= 4)):
                return m.group(0)
            return swap("LEADING_NAME", w, m.group(1))
        t = LEADING.sub(lead, t)

        # 4) Presidio + spaCy PERSON for everyone else, skipping places/orgs and our own fakes
        doc = spacy_nlp(t)
        non_person = [(e.start_char, e.end_char) for e in doc.ents
                      if e.label_ in {"GPE", "LOC", "FAC", "ORG", "NORP", "PRODUCT", "WORK_OF_ART", "LANGUAGE"}]
        res = analyzer.analyze(text=t, language="en", entities=["PERSON"])
        for r in sorted(res, key=lambda r: r.start, reverse=True):
            span = t[r.start:r.end]
            if not span.strip() or "[" in span or "]" in span:
                continue
            name_words = re.findall(r"[A-Z][a-z][a-zA-Z'\-]*", span)
            if not name_words:
                continue
            bare = [w[:-2] if w.endswith("'s") else w for w in name_words]
            # a span that touches one of our fakes is the NER gluing the next
            # capitalised word onto it ("<fake> Sorry", "<fake> Good point")
            if any(w in fakes_made for w in re.findall(r"[A-Za-z][\w'\-]*", span)):
                continue
            if any(w.lower() in NOT_PEOPLE | AMBIGUOUS | common or INTERJECTION.match(w) for w in bare):
                continue
            if re.search(r"\d|\s-\s|[,;:]", span) or span.lstrip().startswith("-"):
                continue
            # camelCase identifiers (MainView, jobViewArray) and 2-letter tokens (Qt) are code
            if any(len(w) < 3 or re.search(r"[a-z][A-Z]", w) for w in span.split()):
                continue
            if any(s <= r.start < e or s < r.end <= e for s, e in non_person):
                continue
            new = fake_person(span)
            found.update(["PERSON"])
            log.append({"row": row, "kind": "PERSON", "real": span, "fake": new})
            t = t[:r.start] + new + t[r.end:]

        # 5) the same handle / name again later in the message, without its "@"
        mine = {w.strip(".,;:!?").lower() for l in log if l["row"] == row for w in l["real"].split()}
        for w in mine:
            w = w[:-2] if w.endswith("'s") else w
            fk = mapping.get(("FIRST", w)) or mapping.get(("LAST", w))
            pat = r"(?<![\w@])" + re.escape(w) + r"(?!\w)"
            if fk and len(w) >= 3 and w not in common and re.search(pat, t, re.I):
                t = re.sub(pat, fk, t, flags=re.I)
                found.update(["REPEAT"])
        return t

    out, dropped = [], Counter()
    for i, (row, text) in enumerate(zip(df["row"], texts)):
        if CODE_AT.search(text):
            out.append(None); dropped["code_at_sign"] += 1
            continue
        s = scrub(row, text)
        # anything still carrying "@" or "User:" (emails, odd handles) is not worth guessing at
        if "@" in s or "User:" in s:
            out.append(None); dropped["at_or_user_left"] += 1
            continue
        out.append(s)
        if (i + 1) % 1000 == 0:
            print(f"  {i+1:,}/{len(df):,}")
    df["original"] = texts
    df["body"] = out
    df = df[df["body"].notna()]
    df = df[df["body"].map(wc).between(MIN_WORDS, MAX_WORDS)]
    pd.DataFrame(log, columns=["row", "kind", "real", "fake"]).to_csv(PII_LOG, index=False)
    # a row where a replaced name is still readable somewhere else is dropped, not patched
    leaky = {row for row, _ in find_leaks(df)}
    dropped["name_still_readable"] = len(leaky)
    df = df[~df["row"].isin(leaky)]
    df.to_csv(WORK / "2_pii.csv", index=False)
    keep_rows = set(df["row"])
    pd.DataFrame([l for l in log if l["row"] in keep_rows],
                 columns=["row", "kind", "real", "fake"]).to_csv(PII_LOG, index=False)
    print("replaced:", dict(found))
    print("dropped:", dict(dropped), f"-> {len(df):,} rows")
    update_counts(pii_replaced=dict(found), pii_dropped=dict(dropped), after_pii=len(df))
    leaks = find_leaks(df)
    print(f"leak check right after scrubbing: {len(leaks)} messages still carry a name that was replaced")


# ---------------------------------------------------------------- PII check
def find_leaks(df):
    """A real handle / name that was replaced somewhere but is still in the row it came from."""
    log = pd.read_csv(PII_LOG) if PII_LOG.exists() else pd.DataFrame(columns=["row", "kind", "real", "fake"])
    by_row = {}
    for row, real in zip(log["row"], log["real"].astype(str)):
        by_row.setdefault(row, set()).add(real)
    hits = []
    for row, body in zip(df["row"], df["body"].astype(str)):
        why = [r for r in by_row.get(row, ())
               if len(r) >= 3 and re.search(r"(?<!\w)" + re.escape(r.strip(".,;:!?")) + r"(?!\w)", body)]
        if "@" in body or "User:" in body:
            why.append("@ or User: left")
        if why:
            hits.append((row, why[:3]))
    return hits


def step_piicheck(a):
    df = pd.read_csv(WORK / "2_pii.csv")
    hits = find_leaks(df)
    print(f"2_pii.csv: {len(hits)} messages with a replaced name still in them")
    for row, why in hits[:15]:
        print(f"   row {row}: {why}")
    total = len(hits)
    for path in [GOLD_OUT, RESERVE_OUT, SOURCE_OUT]:
        if path.exists():
            bad = [r["id"] for r in load_jsonl(path) if "@" in r["source"] or "User:" in r["source"]]
            total += len(bad)
            print(f"{path}: {len(bad)} messages with @ or User: left {bad[:10]}")
    # the rows that had a handle or User: name, for the eyeball check
    log = pd.read_csv(PII_LOG)
    hrows = log[log["kind"].isin(["HANDLE", "USER"])]["row"].unique()
    eye = df[df["row"].isin(hrows)][["row", "original", "body"]]
    eye.to_csv(WORK / "handle_rows_to_eyeball.csv", index=False)
    print(f"{len(eye)} rows had a handle or User: name -> {WORK / 'handle_rows_to_eyeball.csv'}")
    return total


# ---------------------------------------------------------------- 3. near dedupe
def shingles(t, k=5):
    t = re.sub(r"\s+", " ", str(t).lower())
    return {t[i:i + k] for i in range(max(1, len(t) - k + 1))}


def minhash(t):
    from datasketch import MinHash
    m = MinHash(num_perm=128)
    for s in shingles(t):
        m.update(s.encode())
    return m


def step_dedupe(a):
    from datasketch import MinHashLSH
    df = pd.read_csv(WORK / "2_pii.csv")
    lsh = MinHashLSH(threshold=0.85, num_perm=128)
    keep = []
    for i, t in enumerate(df["body"]):
        m = minhash(t)
        if lsh.query(m):
            continue
        lsh.insert(str(i), m)
        keep.append(i)
    df = df.iloc[keep].reset_index(drop=True)
    df.to_csv(WORK / "3_dedupe.csv", index=False)
    print(f"near dedupe: kept {len(df):,}")
    update_counts(after_near_dedupe=len(df))


# ---------------------------------------------------------------- 4. signals
WARNED = re.compile(r"model warned: ([\w, ]+)")


def step_signals(a):
    sys.path.insert(0, str(Path("Src/source").resolve()))
    from pipeline.adapters import tone, politeness, circa
    from pipeline import compose_prompt as cp

    df = pd.read_csv(WORK / "3_dedupe.csv")
    out_path = WORK / "4_signals.jsonl"
    done = {r["row"] for r in load_jsonl(out_path)} if out_path.exists() else set()
    if done:
        print(f"resuming: {len(done):,} rows already scored")
    t0 = time.time()
    with open(out_path, "a", encoding="utf-8") as f:
        for i, rec in enumerate(df.to_dict("records")):
            if rec["row"] in done:
                continue
            if a.max_seconds and time.time() - t0 > a.max_seconds:
                print(f"stopped after {a.max_seconds}s; run the step again to carry on")
                break
            text = str(rec["body"])
            raw = [tone.predict(text), politeness.predict(text), circa.predict(text)]
            # the politeness warnings live in the note, which clean_signals strips
            m = WARNED.search(str(raw[1].get("note", "")))
            warnings = [w.strip() for w in m.group(1).split(",")] if m else []
            f.write(json.dumps({"row": int(rec["row"]), "corpus_id": str(rec["corpus_id"]),
                                "site": rec["site"], "source": text,
                                "signals": cp.clean_signals(raw), "warnings": warnings},
                               ensure_ascii=False) + "\n")
            if (i + 1) % 500 == 0:
                print(f"  {i+1:,}/{len(df):,}")
    rows = load_jsonl(out_path)
    print(f"scored {len(rows):,}/{len(df):,}")
    if len(rows) == len(df):
        labels = Counter((s["model"], s["label"]) for r in rows for s in r["signals"])
        print("label counts:")
        for (m_, l), n in sorted(labels.items()):
            print(f"  {m_:<11} {l:<12} {n:,}")
        print("politeness warnings:", dict(Counter(w for r in rows for w in r["warnings"])))


# ---------------------------------------------------------------- 5. gold + source
NEAR_JACCARD = 0.5
NEAR_CONTAIN = 0.8
MIN_SHINGLES_FOR_CONTAIN = 30


def near_gold(text, gold):
    """Too close to a gold/reserve message: char 5-gram Jaccard >= 0.5, or
    containment >= 0.8 when both texts aren't tiny. Same test as Enron."""
    s = shingles(text)
    for gid, g in gold:
        inter = len(s & g)
        if not inter:
            continue
        j, c = inter / len(s | g), inter / min(len(s), len(g))
        if j >= NEAR_JACCARD or (min(len(s), len(g)) >= MIN_SHINGLES_FOR_CONTAIN and c >= NEAR_CONTAIN):
            return gid
    return None


def is_flagged(r):
    if HEDGES.search(str(r.get("source", ""))):
        return True
    return any(s["model"] in FLAG_RULES and str(s["label"]).lower() in FLAG_RULES[s["model"]]
               for s in r["signals"])


def fmt(rs, start):
    return [{"id": f"stanford_{start + i:05d}", "dataset": "stanford",
             "source": r["source"], "signals": r["signals"],
             "_flagged": is_flagged(r)} for i, r in enumerate(rs)]


def strip_private(rows):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def write_gold_review(gold):
    pd.DataFrame([{"id": g["id"], "flagged": g["_flagged"], "source": g["source"],
                   "keep_or_drop": "", "why": ""} for g in gold]).to_csv(GOLD_REVIEW, index=False)


def step_split(a):
    rows = load_jsonl(WORK / "4_signals.jsonl")
    scored = len(rows)
    rows = [r for r in rows if not DROP_WARNINGS & set(r["warnings"])]
    after_warn = len(rows)
    rows = [r for r in rows if all(s["label"] != "unknown" and s["confidence"] for s in r["signals"])]
    print(f"scored {scored:,} -> no non-English warnings {after_warn:,} -> all three classifiers ran {len(rows):,}")

    flagged = [r for r in rows if is_flagged(r)]
    clear = [r for r in rows if not is_flagged(r)]
    print(f"flagged {len(flagged):,}, clear {len(clear):,}")

    random.seed(SEED)
    picked_f = random.sample(flagged, N_GOLD_FLAGGED + N_RES_FLAGGED)
    picked_c = random.sample(clear, N_GOLD_CLEAR + N_RES_CLEAR)
    gold = picked_f[:N_GOLD_FLAGGED] + picked_c[:N_GOLD_CLEAR]
    reserve = picked_f[N_GOLD_FLAGGED:] + picked_c[N_GOLD_CLEAR:]
    held = gold + reserve        # reserves are held out too, in case they get swapped into gold
    held_rows = {r["row"] for r in held}

    held_sh = [(r["row"], shingles(r["source"])) for r in held]
    pool = [r for r in rows if r["row"] not in held_rows and not near_gold(r["source"], held_sh)]
    near_removed = len(rows) - len(held) - len(pool)

    pf = [r for r in pool if is_flagged(r)]
    pc = [r for r in pool if not is_flagged(r)]
    if len(pf) < N_SRC_FLAGGED or len(pc) < N_SRC_CLEAR:
        raise SystemExit(f"pool too small: {len(pf)} flagged / {len(pc)} clear left for the source")
    source = random.sample(pf, N_SRC_FLAGGED) + random.sample(pc, N_SRC_CLEAR)
    random.shuffle(source)

    gold_rows, reserve_rows = fmt(gold, GOLD_START), fmt(reserve, RESERVE_START)
    save_jsonl(strip_private(gold_rows), GOLD_OUT)
    save_jsonl(reserve_rows, RESERVE_OUT)
    save_jsonl(strip_private(fmt(source, SOURCE_START)), SOURCE_OUT)
    idmap = {}
    for rs, start in [(gold, GOLD_START), (reserve, RESERVE_START), (source, SOURCE_START)]:
        for i, r in enumerate(rs):
            idmap[f"stanford_{start + i:05d}"] = r["corpus_id"]
    json.dump(idmap, open(IDMAP_OUT, "w"), indent=0)
    write_gold_review(gold_rows)

    assert not any(near_gold(r["source"], held_sh) for r in source), "near copy of gold in source!"
    for r in load_jsonl(SOURCE_OUT) + load_jsonl(GOLD_OUT):
        assert set(r) == {"id", "dataset", "source", "signals"}

    def sites(rs):
        return dict(Counter(r["site"] for r in rs))
    update_counts(scored=scored, after_non_english_drop=after_warn, after_failed_signal_drop=len(rows),
                  pool_flagged=len(flagged), pool_clear=len(clear),
                  gold=len(gold), gold_flagged=N_GOLD_FLAGGED, gold_clear=N_GOLD_CLEAR,
                  gold_reserve=len(reserve), near_dupes_of_gold_removed=near_removed,
                  source=len(source), source_flagged=N_SRC_FLAGGED, source_clear=N_SRC_CLEAR,
                  site_mix={"gold": sites(gold), "gold_reserve": sites(reserve), "source": sites(source)})
    print(f"\nsaved {GOLD_OUT} ({len(gold)}), {SOURCE_OUT} ({len(source)}), reserves {RESERVE_OUT} ({len(reserve)})")
    print(f"near copies of gold/reserves removed from the pool: {near_removed}")
    print(f"site mix: gold {sites(gold)}, source {sites(source)}")
    print(f"\nnow read every gold message in {GOLD_REVIEW} and note the ids to drop, then run swapgold")


def step_swapgold(a):
    drop = [x.strip() for x in a.drop.split(",") if x.strip()]
    gold = load_jsonl(GOLD_OUT)
    reserve = load_jsonl(RESERVE_OUT)
    used_path = WORK / "reserve_used.json"
    used = set(json.load(open(used_path))) if used_path.exists() else set()
    by_id = {g["id"]: i for i, g in enumerate(gold)}
    for gid in drop:
        if gid not in by_id:
            raise SystemExit(f"{gid} isn't in the gold file")
        old = gold[by_id[gid]]
        want_flag = is_flagged(old)
        rep = next((r for r in reserve if r["id"] not in used and r["_flagged"] == want_flag), None)
        if rep is None:
            raise SystemExit(f"ran out of {'flagged' if want_flag else 'clear'} reserves")
        used.add(rep["id"])
        if IDMAP_OUT.exists():
            idmap = json.load(open(IDMAP_OUT))
            idmap[gid] = idmap.get(rep["id"], idmap.get(gid))
            json.dump(idmap, open(IDMAP_OUT, "w"), indent=0)
        gold[by_id[gid]] = {"id": gid, "dataset": "stanford", "source": rep["source"], "signals": rep["signals"]}
        print(f"{gid}: swapped in reserve {rep['id']} ({'flagged' if want_flag else 'clear'})")
        print(f"   new text: {rep['source'][:120]!r}")
    save_jsonl(gold, GOLD_OUT)
    json.dump(sorted(used), open(used_path, "w"))
    print(f"\nsaved {GOLD_OUT}. Check the new ones too; run swapgold again for any that are still bad.")


# ---------------------------------------------------------------- 6. self-check
def step_check(a):
    """The checks from the review: run this before pushing."""
    gold, source, reserve = load_jsonl(GOLD_OUT), load_jsonl(SOURCE_OUT), load_jsonl(RESERVE_OUT)
    ok = True

    def report(name, passed, detail=""):
        nonlocal ok
        ok &= bool(passed)
        print(f"  {'PASS' if passed else 'FAIL'}  {name}{' - ' + detail if detail else ''}")

    for name, rows, want_f, want_c, lo in [("gold", gold, N_GOLD_FLAGGED, N_GOLD_CLEAR, GOLD_START),
                                           ("reserve", reserve, N_RES_FLAGGED, N_RES_CLEAR, RESERVE_START),
                                           ("source", source, N_SRC_FLAGGED, N_SRC_CLEAR, SOURCE_START)]:
        print(name)
        f = sum(is_flagged(r) for r in rows)
        report("flagged / clear by the flag rule", (f, len(rows) - f) == (want_f, want_c),
               f"{f} / {len(rows) - f}, want {want_f} / {want_c}")
        if name != "reserve":
            report("keys are exactly id, dataset, source, signals",
                   all(set(r) == {"id", "dataset", "source", "signals"} for r in rows))
        report("ids in order", [r["id"] for r in rows] == [f"stanford_{lo + i:05d}" for i in range(len(rows))])
        report("dataset is 'stanford'", all(r["dataset"] == "stanford" for r in rows))
        sig = [s for r in rows for s in r["signals"]]
        report("three signals each, in tone/politeness/circa order",
               all([s["model"] for s in r["signals"]] == ["tone", "politeness", "circa"] for r in rows))
        report("every confidence is a number above 0",
               all(isinstance(s["confidence"], (int, float)) and not isinstance(s["confidence"], bool)
                   and s["confidence"] > 0 for s in sig))
        report("no 'unknown' labels", all(s["label"] != "unknown" for s in sig))
        texts = [r["source"] for r in rows]
        report("no @ left", not any("@" in t for t in texts))
        report("no User: left", not any("User:" in t for t in texts))
        report("no <url> or raw links left",
               not any(re.search(r"<url>|<link>|https?://|www\.", t, re.I) for t in texts))
        report(f"{MIN_WORDS}-{MAX_WORDS} words", all(MIN_WORDS <= wc(t) <= MAX_WORDS for t in texts))
    print("across files")
    # a reserve that swapgold moved into gold is the same message under two ids
    # on purpose, so it is left out of the duplicate checks
    used_path = WORK / "reserve_used.json"
    used = set(json.load(open(used_path))) if used_path.exists() else set()
    spare = [r for r in reserve if r["id"] not in used]
    ids = [r["id"] for r in gold + reserve + source]
    report("ids unique", len(ids) == len(set(ids)))
    hashes = [norm_hash(r["source"]) for r in gold + spare + source]
    report("no message appears twice", len(hashes) == len(set(hashes)),
           f"{len(used)} reserves swapped into gold" if used else "")
    held = [(r["id"], shingles(r["source"])) for r in gold + reserve]
    near = [r["id"] for r in source if near_gold(r["source"], held)]
    report("no near-copy of gold or reserves in source", not near, ", ".join(near[:5]))
    idmap = json.load(open(IDMAP_OUT))
    report("id map covers every id", set(idmap) == set(ids))
    live = [v for k, v in idmap.items() if k not in used]
    report("no corpus row used twice", len(set(live)) == len(live))
    print("\nALL CHECKS PASS" if ok else "\nSOMETHING FAILED - fix before pushing")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["clean", "pii", "piicheck", "dedupe", "signals", "split", "check", "swapgold"])
    ap.add_argument("--drop", default="", help="swapgold: comma-separated gold ids to replace")
    ap.add_argument("--max-seconds", type=int, default=0,
                    help="signals: stop after this many seconds (run again to resume)")
    a = ap.parse_args()
    {"clean": step_clean, "pii": step_pii, "piicheck": step_piicheck, "dedupe": step_dedupe,
     "signals": step_signals, "split": step_split, "check": step_check,
     "swapgold": step_swapgold}[a.step](a)
