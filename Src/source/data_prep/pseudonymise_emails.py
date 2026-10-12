"""Pseudonymise the email addresses in the repo's data CSVs (privacy test PT-14).

    python Src/source/data_prep/pseudonymise_emails.py \\
        data/processed/enron_tone_eval_human.csv data/processed/enron_tone_labeled.csv \\
        data/processed/stanford_politeness_output.csv \\
        data/Stanford_Politeness/stanford_politeness_clean.csv \\
        data/Stanford_Politeness/stanford_politeness_features.csv
    python Src/source/data_prep/pseudonymise_emails.py --check data/processed/*.csv data/Stanford_Politeness/*.csv

Addresses become [EMAIL_0001], [EMAIL_0002], ... One mapping covers all the files
given, so an address gets the same pseudonym wherever it appears in that run. Numbers
carry on after the highest pseudonym already in the files and go by first appearance,
not alphabetically, so they say nothing about the name. The mapping is never written
anywhere.

    from_, to   address lists; display names ("legal <.taylor@enron.com>") go too
    subject     addresses inside the text
    Request     (Stanford) user@domain.tld addresses only; "pick-an-email@domain" in
                an example is not someone's address
    body        Lotus Notes entries that still hold a name ("Jeff Skilling/Corp/Enron@ENRON",
                "[PERSON_REDACTED] Dasovich@ENRON") and plain addresses. Entries the
                earlier scrub already redacted ("[PERSON_REDACTED]/ECT@ECT") hold nothing
                personal and stay as they are, as does "@" used for "at".

message_id is never touched: it is how enron_register.py and enron_step1.py keep the
human-labelled eval rows out of training. enron_register.py also compares body hashes,
but against its unscrubbed staging corpus, so a body the earlier scrub already redacted
could not match there before this script either; message_id is what holds.

The csv module reproduces these files byte for byte, so only the cells that held an
address change. A file it wouldn't reproduce exactly is refused rather than rewritten.

--check counts what PT-14 counted - unique user@domain.tld values in any column but
message_id - and exits 1 if there are any.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path
from typing import Callable

NOT_CHECKED = {"message_id"}

# What PT-14 flags.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Wider, for headers and subjects: apostrophes ("nicholas.o'day@enron.com") and Enron's
# internal addresses with no top-level domain ("Cougars@Enron"). A pattern rather than
# email.utils.getaddresses, whose strictness changed between Pythons.
ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+'!#$&*=?^`{|}~/-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
# Lotus Notes entries in bodies: an optional first name or initial, the surname (or the
# earlier scrub's [PERSON_REDACTED]), the routing path, then @domain. Lotus wrapped its
# recipient lists, so one line break can fall between the first name and the surname -
# one, not several: a sign-off above a blank line is a different thing.
_NAME, _INITIAL = r"[A-Z][A-Za-z'-]+", r"[A-Z]\.?"
LOTUS_RE = re.compile(
    rf"(?<![\w\]/@])(?P<first>(?:{_NAME}|{_INITIAL})(?:[ \t]+{_INITIAL})?(?:[ \t]+\n?|\n)[ \t]*)?"
    rf"(?P<last>{_NAME}|\[PERSON_REDACTED\])(?:/(?:[A-Za-z&]+|\[ORG_REDACTED\]))*"
    rf"@(?:[A-Za-z_]+|\[ORG_REDA[^\s,;]*)")
# A plain lower-case address in a body ("wcs@modrallcom.", a correspondent's initials).
LOWER_ADDRESS_RE = re.compile(r"(?<![\w\]/@])[a-z][\w.'-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
PSEUDONYM_RE = re.compile(r"\[EMAIL_(\d+)\]")


class Pseudonyms:
    """One shared mapping: the same address always gets the same pseudonym."""

    def __init__(self, start: int = 0) -> None:
        self._map: dict[str, str] = {}
        self._start = start

    def __call__(self, address: str) -> str:
        key = re.sub(r"\s+", " ", address.strip("'\"")).lower()
        if key not in self._map:
            self._map[key] = f"[EMAIL_{self._start + len(self._map) + 1:04d}]"
        return self._map[key]

    def __len__(self) -> int:
        return len(self._map)


def address_list(value: str, pseudonym: Pseudonyms) -> str:
    """"a@x.com, legal <b@x.com>" -> "[EMAIL_0001], [EMAIL_0002]"."""
    found = ADDRESS_RE.findall(value)
    return ", ".join(pseudonym(a) for a in found) if found else value


def in_text(value: str, pseudonym: Pseudonyms) -> str:
    """Addresses inside free text, the words around them kept."""
    return ADDRESS_RE.sub(lambda m: pseudonym(m.group(0)), value)


def strict_in_text(value: str, pseudonym: Pseudonyms) -> str:
    """Only what PT-14 counts as an address: user@domain.tld."""
    return EMAIL_RE.sub(lambda m: pseudonym(m.group(0)), value)


def holds_a_name(m: re.Match) -> bool:
    """A LOTUS_RE match the earlier scrub didn't fully redact."""
    return not (m.group("first") is None and m.group("last") == "[PERSON_REDACTED]")


def in_body(value: str, pseudonym: Pseudonyms) -> str:
    """Named Lotus entries and plain addresses; fully redacted entries stay."""
    value = LOTUS_RE.sub(lambda m: pseudonym(m.group(0)) if holds_a_name(m) else m.group(0), value)
    value = EMAIL_RE.sub(lambda m: pseudonym(m.group(0)), value)
    return LOWER_ADDRESS_RE.sub(lambda m: pseudonym(m.group(0)), value)


HANDLERS: dict[str, Callable[[str, Pseudonyms], str]] = {
    "from_": address_list, "to": address_list, "subject": in_text, "Request": strict_in_text, "body": in_body,
}


def load(path: Path) -> tuple[list[list[str]], str]:
    csv.field_size_limit(sys.maxsize)          # whole email threads sit in one cell
    text = path.read_bytes().decode("utf-8")
    # From the header row: email bodies inside quoted cells carry their own \r\n.
    newline = "\r\n" if text.split("\n", 1)[0].endswith("\r") else "\n"
    return list(csv.reader(io.StringIO(text, newline=""))), newline


def render(rows: list[list[str]], newline: str) -> bytes:
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator=newline).writerows(rows)
    return buf.getvalue().encode("utf-8")


def pseudonymise(rows: list[list[str]], pseudonym: Pseudonyms) -> list[list[str]]:
    header = rows[0]
    columns = {header.index(c): handler for c, handler in HANDLERS.items() if c in header}
    out = [header]
    for row in rows[1:]:
        row = list(row)
        for i, handler in columns.items():
            if i < len(row):
                row[i] = handler(row[i], pseudonym)
        out.append(row)
    return out


def email_like(rows: list[list[str]]) -> set[str]:
    """PT-14's count: unique user@domain.tld values in any column but message_id."""
    checked = [i for i, c in enumerate(rows[0]) if c not in NOT_CHECKED]
    return {m for row in rows[1:] for i in checked if i < len(row) for m in EMAIL_RE.findall(row[i])}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--check", action="store_true", help="count email-like values, change nothing")
    a = p.parse_args(argv)

    if a.check:
        found = 0
        for path in a.files:
            n = len(email_like(load(path)[0]))
            print(f"{path}: {n} unique email-like values")
            found += n
        return 1 if found else 0

    loaded = [(path, *load(path)) for path in a.files]
    for path, rows, newline in loaded:
        if render(rows, newline) != path.read_bytes():
            sys.exit(f"{path}: the csv module doesn't reproduce it byte for byte; not rewriting it")
    start = max((int(n) for _, rows, _ in loaded for row in rows for cell in row
                 for n in PSEUDONYM_RE.findall(cell)), default=0)
    pseudonym = Pseudonyms(start)
    for path, rows, newline in loaded:
        new = pseudonymise(rows, pseudonym)
        path.write_bytes(render(new, newline))
        changed = sum(1 for old, row in zip(rows, new) if old != row)
        print(f"{path}: {len(email_like(rows))} unique email-like values -> {len(email_like(new))}, "
              f"{changed} rows changed")
    print(f"{len(pseudonym)} addresses pseudonymised; the mapping is not saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
