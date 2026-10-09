"""
enron_step1.py
Step 1 of the final build guide for Enron: turn the cleaned corpus into
  data/gold/enron_gold.jsonl     (60 messages, human-checked, never touched again)
  data/source/enron_source.jsonl (~1,000 messages with signals)

v3, after Sanket's review of #13:
  - PII: Enron header names ("Sara Shackleton/HOU/ECT@ECT", "Name@ENRON"),
    "Last, First" and known employee names are now caught on top of Presidio,
    plus a wider phone pattern. New `piicheck` step reports anything left.
  - the scrub keeps line breaks and spacing, and skips places / companies
  - junk filter: spam, leftover forwarded headers, signature-only blocks and
    trading lines are dropped before sampling
  - gold near-copies: exact similarity check against every gold message
  - gold gets a reserve list so junk gold can be swapped by hand (`swapgold`)

Run from the repo root, one step at a time:

  python Src/source/model/tone/enron_step1.py clean      # body only, 5-120 words, no automated/junk mail, exact dedupe
  python Src/source/model/tone/enron_step1.py pii        # header names + Presidio + phones -> consistent fakes
  python Src/source/model/tone/enron_step1.py piicheck   # should report 0 leaks
  python Src/source/model/tone/enron_step1.py dedupe     # near duplicates with MinHash (0.85)
  python Src/source/model/tone/enron_step1.py signals    # run the three pipeline adapters
  python Src/source/model/tone/enron_step1.py split      # 60 gold + reserves first, then ~1,000 source
  python Src/source/model/tone/enron_step1.py swapgold --drop enron_00003,enron_00008

Flagged = politeness low OR circa indirect (terse isn't a tone label anymore).
"""

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[3]))   # repo root, for Src.source.*
from enron_register import clean_body   # same quoted-reply / signature cutting as before

CORPUS = "data/staging/enron_cleaned.csv"
OLD_GOLD = "data/processed/enron_tone_eval_human.csv"   # old tone eval rows, kept out too
WORK = Path("data/step1")
GOLD_OUT = Path("data/gold/enron_gold.jsonl")
SOURCE_OUT = Path("data/source/enron_source.jsonl")
RESERVE_OUT = WORK / "gold_reserve.jsonl"
GOLD_REVIEW = WORK / "gold_review.csv"
COUNTS_OUT = WORK / "counts.json"
NAMES_OUT = WORK / "known_names.json"

# The flag rule and the selection targets are shared by every dataset's
# step 1, so they live in one place: Src/source/data_prep/flag_rule.py.
from Src.source.data_prep.flag_rule import (  # noqa: E402
    FLAG_RULES, HEDGES, SEED, is_flagged,
    N_GOLD_FLAGGED, N_GOLD_CLEAR, N_RES_FLAGGED, N_RES_CLEAR, N_SRC_FLAGGED, N_SRC_CLEAR,
)

# ---------------------------------------------------------------- helpers
AUTOMATED = re.compile(
    r"unsubscribe|newsletter|mailing list|click here|view this (?:e-?mail|message) (?:in|online)"
    r"|this (?:e-?mail|message) was (?:sent|generated) (?:automatically|by)|do not reply"
    r"|auto(?:matic)?[- ]?reply|out of (?:the )?office|calendar entry|invitation:|"
    r"accepted:|declined:|tentative:|has been (?:scheduled|cancelled|rescheduled)"
    r"|^\s*when:.*$\n^\s*where:|you are receiving this|privacy policy|copyright \d{4}",
    re.I | re.M)
AUTOMATED_SENDER = re.compile(r"no-?reply|newsletter|announce|mailer|bounce|digest|alert", re.I)

# ---- junk: not a message one colleague wrote to another
SPAM = re.compile(
    r"mortgage|refinanc|viagra|lowest rates?|act now|limited time|special offer|free (?:offer|trial|gift)"
    r"|you(?:'ve| have) (?:won|been selected)|winner|casino|lottery|opt[- ]out|remove (?:me|you) from"
    r"|100% (?:free|guaranteed)|\$\$\$|earn \$|work from home|weight loss|credit (?:report|score)",
    re.I)
HEADER_LINE = re.compile(r"^\s*(?:to|from|cc|bcc|subject|sent|date|re|fw|fwd)\s*:", re.I | re.M)
FORWARD_MARK = re.compile(r"-{3,}|forwarded by|original message|^\s*>", re.I | re.M)
SIG_WORDS = re.compile(
    r"\b(?:vice president|director|manager|analyst|phone|fax|mobile|cell|pager|suite|street|"
    r"st\.|ave\.?|houston|tx|texas|\d{5}(?:-\d{4})?|enron (?:north america|corp|wholesale)|"
    r"smith street|e-?mail)\b", re.I)


def is_junk(text):
    """Returns a reason string if the message isn't a real colleague message."""
    t = str(text)
    if SPAM.search(t):
        return "spam"
    if HEADER_LINE.search(t) or FORWARD_MARK.search(t):
        return "forwarded header"
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    toks = t.split()
    # trading / data lines: lots of numbers, e.g. "Teco Tap 50.000 / HPL Gas Daily"
    num_share = sum(bool(re.search(r"\d", w)) for w in toks) / max(len(toks), 1)
    if num_share >= 0.3:
        return "trading/data lines"
    # a real message has at least one sentence-ish line: 4+ words, 2+ ordinary
    # lowercase words (punctuation stripped, so "file." still counts)
    def plain(w):
        w = w.strip(".,!?;:()\"'")
        return w.isalpha() and w.islower()
    sentenceish = [l for l in lines if len(l.split()) >= 4
                   and sum(plain(w) for w in l.split()) >= 2]
    if not sentenceish:
        if any(SIG_WORDS.search(l) for l in lines):
            return "signature block"
        return "no sentence"
    # mostly a signature block with one short line on top
    sig_lines = sum(bool(SIG_WORDS.search(l)) for l in lines)
    if len(lines) >= 4 and sig_lines / len(lines) >= 0.5:
        return "signature block"
    return None


def norm_hash(t):
    t = re.sub(r"[^\w\s]", "", str(t).lower())
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()


def wc(t):
    return len(str(t).split())


def save_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_jsonl(path):
    return [json.loads(l) for l in open(path)]


def update_counts(**kw):
    c = json.load(open(COUNTS_OUT)) if COUNTS_OUT.exists() else {}
    c.update(kw)
    json.dump(c, open(COUNTS_OUT, "w"), indent=2)


# ---------------------------------------------------------------- 1. clean
# header columns are already Person_N, so harvest real names from the raw text
ROUTE_NAME = re.compile(r"([A-Z][a-z]+)\s+(?:[A-Z]\.?\s+)?([A-Z][a-z][a-zA-Z'-]*)\s*"
                        r"(?:/[A-Z]{2,6})+@[A-Za-z_]+")
AT_NAME = re.compile(r"([A-Z][a-z]+)\s+([A-Z][a-z][a-zA-Z'-]*)@(?:ENRON|ECT|EES|ENRON_DEVELOPMENT)\b")
HEADER_LINE_NAMES = re.compile(r"^\s*(?:to|from|cc|bcc)\s*:(.*)$", re.I | re.M)
FULL = re.compile(r"\b([A-Z][a-z]+)\s+(?:[A-Z]\.?\s+)?([A-Z][a-z][a-zA-Z'-]*)\b")
LAST_FIRST = re.compile(r"\b([A-Z][a-z][a-zA-Z'-]*),\s+([A-Z][a-z]+)\b")


def common_words(texts, min_lower=5, share=0.15):
    """Words that show up in lowercase a fair bit ("report", "order", "the") are
    ordinary words, not names, even if they appear capitalised in a header line."""
    lower, total = Counter(), Counter()
    for t in texts:
        for w in re.findall(r"[A-Za-z][a-z]+", str(t)):
            lw = w.lower()
            total[lw] += 1
            if w == lw:
                lower[lw] += 1
    return {w for w, c in lower.items() if c >= min_lower and c / total[w] >= share}


def harvest_names(texts):
    pairs = Counter()
    for t in texts:
        t = str(t)
        for f, l in ROUTE_NAME.findall(t):
            pairs[(f.lower(), l.lower())] += 1
        for f, l in AT_NAME.findall(t):
            pairs[(f.lower(), l.lower())] += 1
        for line in HEADER_LINE_NAMES.findall(t):
            for l, f in LAST_FIRST.findall(line):
                pairs[(f.lower(), l.lower())] += 1
            for f, l in FULL.findall(line):
                pairs[(f.lower(), l.lower())] += 1
    bad = NOT_PEOPLE | AMBIGUOUS
    return {(f, l) for (f, l), c in pairs.items()
            if c >= 3 and len(f) >= 3 and len(l) >= 3 and f not in bad and l not in bad}


def step_clean(a):
    WORK.mkdir(parents=True, exist_ok=True)
    print("reading corpus...")
    cols = ["message_id", "from_", "subject", "body", "raw_body"]
    df = pd.read_csv(CORPUS, usecols=lambda c: c in cols)
    start = len(df)

    raw_col = "raw_body" if "raw_body" in df else "body"
    pairs = harvest_names(df[raw_col].dropna())
    common = common_words(df["body"].dropna())
    before = len(pairs)
    pairs = {(f, l) for f, l in pairs if f not in common and l not in common}
    print(f"dropped {before - len(pairs):,} harvested 'names' that are ordinary words (report, order...)")
    known = {"first": sorted({f for f, _ in pairs}), "last": sorted({l for _, l in pairs}),
             "pairs": sorted(f"{f} {l}" for f, l in pairs)}
    json.dump(known, open(NAMES_OUT, "w"))
    print(f"known employee names harvested from the raw emails: {len(pairs):,} people")
    if "raw_body" in df:
        df = df.drop(columns=["raw_body"])

    df["body"] = df["body"].map(clean_body)
    df = df[df["body"].map(wc).between(5, 120)]
    after_len = len(df)

    auto = df["body"].str.contains(AUTOMATED) | df["subject"].fillna("").str.contains(AUTOMATED)
    if "from_" in df:
        auto |= df["from_"].fillna("").str.contains(AUTOMATED_SENDER)
    df = df[~auto]
    after_auto = len(df)

    df["junk"] = df["body"].map(is_junk)
    junk_counts = df["junk"].value_counts().to_dict()
    df = df[df["junk"].isna()]
    after_junk = len(df)

    df["h"] = df["body"].map(norm_hash)
    df = df.drop_duplicates("h")

    if Path(OLD_GOLD).exists():
        old = pd.read_csv(OLD_GOLD)
        df = df[~df["message_id"].isin(set(old["message_id"]))]

    pool = df.sample(n=min(a.pool, len(df)), random_state=SEED).reset_index(drop=True)
    pool[["message_id", "body"]].to_csv(WORK / "1_clean.csv", index=False)

    print(f"corpus {start:,} -> 5-120 words {after_len:,} -> no automated {after_auto:,} "
          f"-> no junk {after_junk:,} -> exact dedupe {len(df):,} -> pool {len(pool):,}")
    print("junk dropped:", junk_counts)
    update_counts(corpus=start, after_length=after_len, after_automated=after_auto,
                  after_junk=after_junk, junk_dropped=junk_counts,
                  after_exact_dedupe=len(df), pool=len(pool))


# ---------------------------------------------------------------- 2. PII
# words that look like names to the NER but aren't people here
TITLES_PLACES = {
    "san", "francisco", "new", "york", "los", "angeles", "las", "vegas", "salt", "lake", "city",
    "senior", "director", "vice", "president", "manager", "managing", "associate", "assistant",
    "executive", "chief", "officer", "general", "counsel", "legal", "analyst", "specialist",
    "north", "america", "americas", "global", "national", "international", "american", "united",
    "states", "corporate", "group", "office", "department", "division", "team", "desk",
}
NOT_PEOPLE = {
    "houston", "portland", "calgary", "london", "omaha", "dallas", "austin", "denver", "chicago",
    "sacramento", "california", "texas", "oregon", "enron", "ect", "hou", "ees", "ena", "corp",
    "hpl", "teco", "tap", "gas", "daily", "power", "energy", "capital", "trading", "risk",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "thanks", "regards", "cheers", "hi", "hello", "dear",
    # address-list words that aren't names (enron.announcements@enron.com etc.)
    "team", "info", "admin", "announcements", "news", "support", "help", "service", "services",
    "list", "group", "dept", "office", "center", "mail", "web", "online", "trading", "legal",
    "research", "operations", "desk", "account", "accounts", "billing", "payroll", "benefits",
}
# first/last names that are also everyday words - only replaced when the NER
# or a header pattern says they're a person, never on their own
AMBIGUOUS = {
    "mark", "bill", "will", "may", "june", "april", "grant", "rich", "joy", "pat", "sue", "art",
    "don", "guy", "ray", "frank", "chuck", "dawn", "faith", "hope", "rose", "holly", "ivy",
    "iris", "amber", "price", "young", "white", "brown", "black", "green", "hall", "king",
    "long", "ward", "day", "rice", "lay", "bass", "fox", "hunt", "ross", "lane", "rock",
    "case", "small", "best", "hill", "stone", "wood", "power", "gas", "cash", "bond", "gold",
    "major", "love", "west", "north", "south", "east", "dean", "baker", "cook",
}
NAMEY_AMBIGUOUS = {
    "mark", "bill", "joy", "pat", "sue", "art", "don", "ray", "frank", "chuck", "dawn", "faith",
    "hope", "rose", "holly", "ivy", "iris", "amber", "dean", "guy", "rich", "grant",
}


def ambiguous_name_spans(t, real_first):
    """(start, end) of everyday-word names that are clearly used as a name here."""
    spans = []
    for m in re.finditer(r"\b[A-Z][a-z]+\b", t):
        w = m.group(0).lower()
        if w not in NAMEY_AMBIGUOUS:      # the harvest skips these words, so no list check
            continue
        before = t[:m.start()]
        after = t[m.end():]
        line_before = before.split("\n")[-1]
        line_after = after.split("\n")[0]
        alone_on_line = not line_before.strip() and not line_after.strip(" .,-")
        after_greeting = re.search(r"(?:thanks|thank you|hi|hey|hello|dear|regards|cheers|best|--|-)[\s,]*$",
                                   line_before, re.I)
        line_label = not line_before.strip() and line_after.startswith(":")
        mid_sentence = (re.search(r"[a-z,]\s+$", before) is not None
                        and re.match(r"\s+[a-z]", after) is not None)
        if alone_on_line or after_greeting or line_label or mid_sentence:
            spans.append((m.start(), m.end()))
    return spans


PLACE_AFTER = re.compile(
    r"(?:'s)?\s+(?:Bay|Street|St\.?|Center|Centre|Park|Island|Point|Building|Tower|Plaza|Road|Rd\.?"
    r"|Avenue|Ave\.?|Hall|Field|Hotel|Club|Lake|River|Valley|Heights|Square|Station|Plant|Unit)\b")
PHONE = re.compile(
    # optional +1, area code as (713) / 713) / 713, then 646-8531 style, optional extension.
    # no word boundary needed before "(", so "Number(713) 646-8531" and "503) 464-7404" match too
    r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)|\d{3})[\s.-]*\d{3}[\s.-]\d{4}"
    r"(?:\s*(?:x|ext\.?)\s*\d{1,5})?(?!\d)",
    re.I,
)


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

    known = json.load(open(NAMES_OUT)) if NAMES_OUT.exists() else {"first": [], "last": [], "pairs": []}
    known = clean_known(known)
    k_first = {n for n in known["first"] if n not in AMBIGUOUS and n not in NOT_PEOPLE}
    k_last = {n for n in known["last"] if n not in AMBIGUOUS and n not in NOT_PEOPLE}
    k_pairs = {tuple(p.split()) for p in known["pairs"]}
    # fakes must never be a real Enron name, otherwise a real "David Scott"
    # gets skipped because "David" is also one of our fakes
    real_first, real_last = set(known["first"]), set(known["last"])

    fake = Faker(); Faker.seed(SEED)
    mapping, fakes_made = {}, set()

    def fake_word(word, slot):
        """one shared dictionary: the same real first/last name always gets the same fake"""
        core = word.strip(".,;:")
        poss = ""
        if core.lower().endswith("'s"):
            core, poss = core[:-2], "'s"
        key = (slot, core.lower())
        if key not in mapping:
            gen = fake.first_name if slot == "FIRST" else fake.last_name
            avoid = real_first | real_last | AMBIGUOUS | NAMEY_AMBIGUOUS | NOT_PEOPLE | TITLES_PLACES
            cand = gen()
            for _ in range(300):
                if cand.lower() not in avoid:
                    break
                cand = gen()
            else:
                cand = cand + "son"      # very unlikely: every try was a real name
            mapping[key] = cand
            fakes_made.add(mapping[key])
        out = mapping[key]
        if core.isupper():
            out = out.upper()
        return word.replace(core + poss, out + poss, 1) if core else word

    def fake_person(span):
        """keeps the original spacing/newlines, only swaps the words themselves"""
        parts = re.split(r"(\s+)", span)
        words = [i for i, p in enumerate(parts) if p and not p.isspace()]
        for n, i in enumerate(words):
            parts[i] = fake_word(parts[i], "FIRST" if n == 0 else "LAST")
        return "".join(parts)

    def fake_phone(real):
        key = ("PHONE", re.sub(r"\D", "", real))
        if key not in mapping:
            mapping[key] = fake.numerify("###-###-####")
        return mapping[key]

    found = Counter()

    # 1) Enron routing headers: "Sara Shackleton/HOU/ECT@ECT", "Kimberly Mann@ENRON"
    hdr = re.compile(r"(?<![/\w])([A-Z][a-z][a-zA-Z'-]*(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z][a-zA-Z'-]*)?)"
                     r"(?=(?:/[A-Z]{2,6}){1,3}@[A-Z_]+|@(?:ENRON|ECT|EES|ENRON_DEVELOPMENT)\b)")
    # 2) "Dasovich, Jeff" - only when one of the two is a known employee name
    last_first = re.compile(r"\b([A-Z][a-z'-]+),\s+([A-Z][a-z]+)\b")

    def scrub(text):
        t = PHONE.sub(lambda m: (found.update(["PHONE_NUMBER"]), fake_phone(m.group(0)))[1], text)

        t = hdr.sub(lambda m: (found.update(["PERSON_HEADER"]), fake_person(m.group(1)))[1], t)

        def lf(m):
            last, first = m.group(1), m.group(2)
            lo_l, lo_f = last.lower(), first.lower()
            if lo_l in NOT_PEOPLE or lo_l in AMBIGUOUS or lo_l in TITLES_PLACES:
                return m.group(0)
            if (lo_f, lo_l) in k_pairs or (lo_l in k_last and lo_f in k_first):
                found.update(["PERSON_LAST_FIRST"])
                return f"{fake_word(last, 'LAST')}, {fake_word(first, 'FIRST')}"
            return m.group(0)
        t = last_first.sub(lf, t)

        # 3) known employee "First Last" pairs
        def known_pair(m):
            f, gap, l = m.group(1), m.group(2), m.group(3)
            if (f.lower(), l.lower()) in k_pairs and f not in fakes_made:
                found.update(["PERSON_KNOWN"])
                return f"{fake_word(f, 'FIRST')}{gap}{fake_word(l, 'LAST')}"
            return m.group(0)
        t = re.sub(r"\b([A-Z][a-z]+)(\s+)([A-Z][a-z'-]+)\b", known_pair, t)

        # 4) Presidio for everyone else, skipping places/companies and our own fakes
        doc = spacy_nlp(t)
        non_person = [(e.start_char, e.end_char) for e in doc.ents if e.label_ in {"GPE", "LOC", "FAC", "ORG", "NORP"}]
        res = analyzer.analyze(text=t, language="en", entities=["PERSON", "EMAIL_ADDRESS"])
        for r in sorted(res, key=lambda r: r.start, reverse=True):
            span = t[r.start:r.end]
            core = span.strip()
            if not core:
                continue
            if r.entity_type == "EMAIL_ADDRESS":
                found.update(["EMAIL_ADDRESS"])
                key = ("EMAIL", core.lower())
                if key not in mapping:
                    mapping[key] = fake.email()
                t = t[:r.start] + span.replace(core, mapping[key]) + t[r.end:]
                continue
            # name-looking words only, so "Name/HOU/ECT@ECT" routing bits are ignored
            name_words = [w for w in re.findall(r"[A-Z][a-z][a-zA-Z'-]*", core)]
            if not name_words or all(w.lower().removesuffix("'s") in NOT_PEOPLE for w in name_words):
                continue
            if all(w.removesuffix("'s") in fakes_made for w in name_words):
                continue      # already one of our fakes from the header / known-name passes
            if any(s <= r.start < e or s < r.end <= e for s, e in non_person):
                continue
            # "Robert's Bay", "Allen Center" - a place named after someone, not a person
            if PLACE_AFTER.match(t[r.end:]):
                continue
            found.update(["PERSON"])
            if re.search(r"[/@]", span):
                m = re.match(r"(\s*)([A-Za-z][A-Za-z.' -]*?)([/@].*)$", span, re.S)
                if m:
                    t = t[:r.start] + m.group(1) + fake_person(m.group(2)) + m.group(3) + t[r.end:]
                    continue
            t = t[:r.start] + fake_person(span) + t[r.end:]

        # 5) stand-alone known first/last names the NER missed ("Vince", "Kay")
        def single(m):
            w = m.group(0)
            lw = w.lower()
            if w in fakes_made or lw in NOT_PEOPLE or lw in AMBIGUOUS:
                return w
            if lw in k_first:
                found.update(["PERSON_KNOWN"]); return fake_word(w, "FIRST")
            if lw in k_last:
                found.update(["PERSON_KNOWN"]); return fake_word(w, "LAST")
            return w
        t = re.sub(r"\b[A-Z][a-z]{2,}\b", single, t)

        # 6) everyday-word names (Dawn, Frank, Bill) when the context says person
        for st, en in reversed(ambiguous_name_spans(t, real_first)):
            if t[st:en] in fakes_made:
                continue          # one of our own fakes, e.g. "Guy"
            found.update(["PERSON_AMBIGUOUS"])
            t = t[:st] + fake_word(t[st:en], "FIRST") + t[en:]
        return t

    df = pd.read_csv(WORK / "1_clean.csv")
    out = []
    for i, text in enumerate(df["body"]):
        out.append(scrub(str(text)))
        if (i + 1) % 1000 == 0:
            print(f"  {i+1:,}/{len(df):,}")
    df["body"] = out
    df.to_csv(WORK / "2_pii.csv", index=False)
    print("replaced:", dict(found))
    update_counts(pii_replaced=dict(found))
    orig = pd.read_csv(WORK / "1_clean.csv")["body"].astype(str).tolist()
    leaks = find_leaks(df["body"].tolist(), known, originals=orig)
    print(f"leak check right after scrubbing: {len(leaks)} messages still look like they have PII")


# ---------------------------------------------------------------- PII check
def clean_known(known):
    bad = TITLES_PLACES | NOT_PEOPLE
    pairs = [p for p in known.get("pairs", []) if not set(p.split()) & bad]
    return {"pairs": pairs, "first": sorted({p.split()[0] for p in pairs}),
            "last": sorted({p.split()[1] for p in pairs})}


def squash(t):
    return re.sub(r"\s+", " ", str(t)).lower()


def find_leaks(texts, known, ids=None, originals=None):
    """Real employee names or phone numbers still in the text. With the
    original text given, a hit only counts if it was in the original too,
    otherwise it is one of our own fakes that shares a name with someone."""
    pairs = {tuple(p.split()) for p in clean_known(known)["pairs"]}
    hits = []
    for i, t in enumerate(texts):
        orig = squash(originals[i]) if originals else None
        orig_digits = re.sub(r"\D", "", originals[i]) if originals else None
        why = []
        for m in re.finditer(r"\b([A-Z][a-z]+)[ \t]+([A-Z][a-z'-]+)\b", t):
            if (m.group(1).lower(), m.group(2).lower()) in pairs:
                why.append(m.group(0))
        for m in re.finditer(r"\b([A-Z][a-z'-]+),[ \t]+([A-Z][a-z]+)\b", t):
            if (m.group(2).lower(), m.group(1).lower()) in pairs:
                why.append(m.group(0))
        phones = [x.group(0) for x in PHONE.finditer(t)]
        if originals:
            why = [w for w in why if squash(w) in orig]
            why += [ph for ph in phones if re.sub(r"\D", "", ph)[-7:] in orig_digits]
            rf = set(clean_known(known)["first"])
            for st, en in ambiguous_name_spans(t, rf):
                w = t[st:en]
                if re.search(r"\b" + re.escape(w) + r"\b", originals[i]):
                    why.append(w)
        else:
            why += [ph for ph in phones if not re.fullmatch(r"\d{3}-\d{3}-\d{4}", ph)]
        if why:
            hits.append(((ids[i] if ids else i), why[:3]))
    return hits


def step_fixphones(a):
    """Swap any phone numbers left in the finished gold, source and reserve files
    for consistent fakes, without re-picking messages (keeps the hand-checked gold)."""
    import hashlib, random as _r
    def fake(real):
        digits = re.sub(r"\D", "", real)
        rng = _r.Random(hashlib.sha1(digits.encode()).hexdigest())
        return re.sub(r"\d", lambda m: str(rng.randint(0, 9)), real)
    for path in ["data/gold/enron_gold.jsonl", "data/source/enron_source.jsonl",
                 "data/step1/gold_reserve.jsonl"]:
        f = Path(path)
        if not f.exists():
            print(f"{path}: missing, skipped"); continue
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        n = 0
        for r in rows:
            new = PHONE.sub(lambda m: fake(m.group(0)), r["source"])
            if new != r["source"]:
                n += 1
                print(f"  {r['id']}: {PHONE.findall(r['source'])}")
                r["source"] = new
        f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{path}: {n} messages fixed")


def step_piicheck(a):
    known = json.load(open(NAMES_OUT))
    orig = pd.read_csv(WORK / "1_clean.csv")
    orig_by_mid = dict(zip(orig["message_id"], orig["body"].astype(str)))
    idmap = json.load(open(WORK / "id_map.json")) if (WORK / "id_map.json").exists() else {}
    targets = []
    if (WORK / "2_pii.csv").exists():
        d = pd.read_csv(WORK / "2_pii.csv")
        targets.append(("2_pii.csv", d["body"].astype(str).tolist(), d["message_id"].tolist(),
                        [orig_by_mid.get(m, "") for m in d["message_id"]]))
    for path in [GOLD_OUT, SOURCE_OUT, RESERVE_OUT]:
        if path.exists() and idmap:
            rows = load_jsonl(path)
            targets.append((str(path), [r["source"] for r in rows], [r["id"] for r in rows],
                            [orig_by_mid.get(idmap.get(r["id"]), "") for r in rows]))
    total = 0
    for name, texts, ids, originals in targets:
        hits = find_leaks(texts, known, ids, originals)
        total += len(hits)
        print(f"{name}: {len(hits)} messages with real PII left")
        for i, why in hits[:15]:
            print(f"   {i}: {why}")
    if not idmap:
        print("(gold/source get checked after the next split, it saves the id map they need)")
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
def load_adapters():
    sys.path.insert(0, str(Path("Src/source").resolve()))
    from pipeline.adapters import tone, politeness, circa
    fns = {}
    for name, mod in [("tone", tone), ("politeness", politeness), ("circa", circa)]:
        fn = None
        for cand in ["run", "predict", "analyze", "classify", "score"]:
            if callable(getattr(mod, cand, None)):
                fn = getattr(mod, cand); break
        if fn is None:
            raise SystemExit(f"couldn't find the function in adapters/{name}.py")
        fns[name] = fn
        print(f"  {name}: using {mod.__name__}.{fn.__name__}")
    return fns


def clean_signal(name, s):
    if not isinstance(s, dict):
        return {"model": name, "label": "unknown", "confidence": 0.0}
    s = {k: s[k] for k in ("model", "label", "confidence") if k in s}
    s.setdefault("model", name)
    s.setdefault("label", "unknown")
    return s


def step_signals(a):
    fns = load_adapters()
    df = pd.read_csv(WORK / "3_dedupe.csv")
    rows = []
    for i, (mid, text) in enumerate(zip(df["message_id"], df["body"])):
        sig = []
        for name in ["tone", "politeness", "circa"]:
            try:
                sig.append(clean_signal(name, fns[name](text)))
            except Exception:
                sig.append({"model": name, "label": "unknown", "confidence": 0.0})
        rows.append({"message_id": mid, "source": text, "signals": sig})
        if (i + 1) % 500 == 0:
            print(f"  {i+1:,}/{len(df):,}")
    save_jsonl(rows, WORK / "4_signals.jsonl")
    labels = Counter((s["model"], s["label"]) for r in rows for s in r["signals"])
    print("label counts:")
    for (m, l), n in sorted(labels.items()):
        print(f"  {m:<11} {l:<12} {n:,}")


# ---------------------------------------------------------------- 5. gold + source
NEAR_JACCARD = 0.5
NEAR_CONTAIN = 0.8
MIN_SHINGLES_FOR_CONTAIN = 30


def near_gold(text, gold):
    """Too close to a gold message: char 5-gram Jaccard >= 0.5, or containment
    >= 0.8 (gold quoted inside a longer email) when both texts aren't tiny."""
    s = shingles(text)
    for gid, g in gold:
        inter = len(s & g)
        if not inter:
            continue
        j, c = inter / len(s | g), inter / min(len(s), len(g))
        if j >= NEAR_JACCARD or (min(len(s), len(g)) >= MIN_SHINGLES_FOR_CONTAIN and c >= NEAR_CONTAIN):
            return gid
    return None


def fmt(rs, start):
    return [{"id": f"enron_{start + i:05d}", "dataset": "enron",
             "source": r["source"], "signals": r["signals"],
             "_flagged": is_flagged(r)} for i, r in enumerate(rs)]


def strip_private(rows):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def write_gold_review(gold):
    pd.DataFrame([{"id": g["id"], "flagged": g["_flagged"], "source": g["source"],
                   "keep_or_drop": "", "why": ""} for g in gold]).to_csv(GOLD_REVIEW, index=False)


def step_split(a):
    rows = load_jsonl(WORK / "4_signals.jsonl")
    flagged = [r for r in rows if is_flagged(r)]
    clear = [r for r in rows if not is_flagged(r)]
    print(f"flagged {len(flagged):,}, clear {len(clear):,}")

    random.seed(SEED)
    picked_f = random.sample(flagged, N_GOLD_FLAGGED + N_RES_FLAGGED)
    picked_c = random.sample(clear, N_GOLD_CLEAR + N_RES_CLEAR)
    gold = picked_f[:N_GOLD_FLAGGED] + picked_c[:N_GOLD_CLEAR]
    reserve = picked_f[N_GOLD_FLAGGED:] + picked_c[N_GOLD_CLEAR:]
    held = gold + reserve        # reserves are held out too, in case they get swapped into gold
    held_ids = {r["message_id"] for r in held}

    held_sh = [(r["message_id"], shingles(r["source"])) for r in held]
    pool = [r for r in rows if r["message_id"] not in held_ids and not near_gold(r["source"], held_sh)]
    near_removed = len(rows) - len(held) - len(pool)

    pf = [r for r in pool if is_flagged(r)]
    pc = [r for r in pool if not is_flagged(r)]
    n_f, n_c = min(N_SRC_FLAGGED, len(pf)), min(N_SRC_CLEAR, len(pc))
    source = random.sample(pf, n_f) + random.sample(pc, n_c)
    random.shuffle(source)

    gold_rows, reserve_rows = fmt(gold, 1), fmt(reserve, 101)
    save_jsonl(strip_private(gold_rows), GOLD_OUT)
    save_jsonl(reserve_rows, RESERVE_OUT)
    save_jsonl(strip_private(fmt(source, 1001)), SOURCE_OUT)
    idmap = {}
    for rs, start in [(gold, 1), (reserve, 101), (source, 1001)]:
        for i, r in enumerate(rs):
            idmap[f"enron_{start + i:05d}"] = r["message_id"]
    json.dump(idmap, open(WORK / "id_map.json", "w"))
    write_gold_review(gold_rows)

    assert not any(near_gold(r["source"], held_sh) for r in source), "near copy of gold in source!"
    for r in load_jsonl(SOURCE_OUT) + load_jsonl(GOLD_OUT):
        assert set(r) == {"id", "dataset", "source", "signals"}

    update_counts(gold=len(gold), gold_reserve=len(reserve),
                  near_dupes_of_gold_removed=near_removed,
                  source=len(source), source_flagged=n_f, source_clear=n_c)
    print(f"\nsaved {GOLD_OUT} ({len(gold)}), {SOURCE_OUT} ({len(source)}), reserves {RESERVE_OUT} ({len(reserve)})")
    print(f"near copies of gold/reserves removed from the pool: {near_removed}")
    print(f"\nnow read every gold message in {GOLD_REVIEW} and note the ids to drop "
          f"(spam, headers, signatures, data lines, broken scrub), then run swapgold")


def step_swapgold(a):
    drop = [x.strip() for x in a.drop.split(",") if x.strip()]
    gold = load_jsonl(GOLD_OUT)
    reserve = load_jsonl(RESERVE_OUT)
    used = set(json.load(open(WORK / "reserve_used.json"))) if (WORK / "reserve_used.json").exists() else set()
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
        idmap_path = WORK / "id_map.json"
        if idmap_path.exists():
            idmap = json.load(open(idmap_path))
            idmap[gid] = idmap.get(rep["id"], idmap.get(gid))
            json.dump(idmap, open(idmap_path, "w"))
        gold[by_id[gid]] = {"id": gid, "dataset": "enron", "source": rep["source"], "signals": rep["signals"]}
        print(f"{gid}: swapped in reserve {rep['id']} ({'flagged' if want_flag else 'clear'})")
        print(f"   new text: {rep['source'][:120]!r}")
    save_jsonl(gold, GOLD_OUT)
    json.dump(sorted(used), open(WORK / "reserve_used.json", "w"))
    print(f"\nsaved {GOLD_OUT}. Check the new ones too; run swapgold again for any that are still bad.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["clean", "pii", "piicheck", "dedupe", "signals", "split", "swapgold", "fixphones"])
    ap.add_argument("--pool", type=int, default=10000,
                    help="how many cleaned emails go through PII + adapters")
    ap.add_argument("--drop", default="", help="swapgold: comma-separated gold ids to replace")
    a = ap.parse_args()
    {"clean": step_clean, "pii": step_pii, "piicheck": step_piicheck, "dedupe": step_dedupe,
     "signals": step_signals, "split": step_split, "swapgold": step_swapgold, "fixphones": step_fixphones}[a.step](a)
