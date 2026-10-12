"""Pseudonymise the email addresses in the tone CSVs (privacy test PT-14).

    python Src/source/data_prep/pseudonymise_emails.py \\
        data/processed/enron_tone_eval_human.csv data/processed/enron_tone_labeled.csv
    python Src/source/data_prep/pseudonymise_emails.py --check data/processed/*.csv

Every address in `from_`, `to` and `subject` becomes [EMAIL_0001], [EMAIL_0002], ...
One mapping covers all the files given, so an address gets the same pseudonym in both
files and in every column. Numbers go by first appearance, not alphabetically, so they
say nothing about the name, and the mapping is never written anywhere. Display names in
`from_`/`to` ("legal <.taylor@enron.com>") go with their addresses.

Left alone on purpose:
  body        PT-14 found no addresses there (enron_prep.py redacted them), and
              enron_register.py hashes bodies to keep the human-labelled eval rows out
              of training - changing them would loosen that guard.
  message_id  the other half of the guard. Its "@thyme" is Enron's mail server, not a
              person.

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

ADDRESS_COLUMNS = ("from_", "to")
TEXT_COLUMNS = ("subject",)
NOT_CHECKED = {"message_id"}

# What PT-14 flags.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Wider, for finding what to replace: apostrophes ("nicholas.o'day@enron.com") and
# Enron's internal addresses with no top-level domain ("Cougars@Enron"). A pattern
# rather than email.utils.getaddresses, whose strictness changed between Pythons.
ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+'!#$&*=?^`{|}~/-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")


class Pseudonyms:
    """One shared mapping: the same address always gets the same pseudonym."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}

    def __call__(self, address: str) -> str:
        key = address.strip("'\"").lower()
        if key not in self._map:
            self._map[key] = f"[EMAIL_{len(self._map) + 1:04d}]"
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


def load(path: Path) -> tuple[list[list[str]], str]:
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
    columns = {c: header.index(c) for c in ADDRESS_COLUMNS + TEXT_COLUMNS if c in header}
    out = [header]
    for row in rows[1:]:
        row = list(row)
        for column, i in columns.items():
            if i < len(row):
                change = address_list if column in ADDRESS_COLUMNS else in_text
                row[i] = change(row[i], pseudonym)
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

    pseudonym = Pseudonyms()
    for path in a.files:
        rows, newline = load(path)
        if render(rows, newline) != path.read_bytes():
            sys.exit(f"{path}: the csv module doesn't reproduce it byte for byte; not rewriting it")
        new = pseudonymise(rows, pseudonym)
        path.write_bytes(render(new, newline))
        changed = sum(1 for old, row in zip(rows, new) if old != row)
        print(f"{path}: {len(email_like(rows))} unique email-like values -> {len(email_like(new))}, "
              f"{changed} rows changed")
    print(f"{len(pseudonym)} addresses pseudonymised; the mapping is not saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
