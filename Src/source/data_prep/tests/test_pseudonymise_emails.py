"""Tests for pseudonymise_emails.py (privacy test PT-14), plus a guard that the
processed data in the repo holds no email addresses."""
import csv
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
_spec = importlib.util.spec_from_file_location("pseudonymise_emails", HERE.parent / "pseudonymise_emails.py")
pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe)

HEADER = ["from_", "to", "subject", "date", "message_id", "body", "label"]


def _write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows([HEADER] + rows)


def _read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_an_address_gets_one_pseudonym_across_files_and_columns(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    _write(a, [["sara.shackleton@enron.com", "jeff.dasovich@enron.com", "Hi", "d", "<1@thyme>", "x", "formal"]])
    _write(b, [["Jeff.Dasovich@enron.com", "sara.shackleton@enron.com, tana.jones@enron.com",
                "Access Request for tana.jones@enron.com", "d", "<2@thyme>", "y", "casual"]])
    assert pe.main([str(a), str(b)]) == 0
    ra, rb = _read(a)[0], _read(b)[0]
    assert (ra["from_"], ra["to"]) == ("[EMAIL_0001]", "[EMAIL_0002]")     # numbered by first appearance
    assert rb["from_"] == "[EMAIL_0002]"                                      # case doesn't matter
    assert rb["to"] == "[EMAIL_0001], [EMAIL_0003]"
    assert rb["subject"] == "Access Request for [EMAIL_0003]"


def test_display_names_and_odd_addresses_go_too(tmp_path):
    f = tmp_path / "f.csv"
    _write(f, [["legal <.taylor@enron.com>", "nicholas.o'day@enron.com, Cougars@Enron",
                "Get FREE CDs@ColumbiaHouse.com! (open for details)", "d", "<3@thyme>", "x", "casual"]])
    pe.main([str(f)])
    row = _read(f)[0]
    assert row["from_"] == "[EMAIL_0001]"
    assert row["to"] == "[EMAIL_0002], [EMAIL_0003]"
    assert row["subject"] == "Get FREE [EMAIL_0004]! (open for details)"


def test_body_message_id_and_labels_are_untouched(tmp_path):
    # The body and message_id are how enron_register.py keeps eval rows out of training.
    f = tmp_path / "f.csv"
    body = "Please call me. [EMAIL_REDACTED] cc Dasovich@ENRON"
    _write(f, [["a@enron.com", "", "Re: lunch", "2001-05-14", "<4.JavaMail.evans@thyme>", body, "formal"],
               ["", "", "no address here", "2001-05-15", "<5.JavaMail.evans@thyme>", "hi", "casual"]])
    before = f.read_bytes().splitlines()
    pe.main([str(f)])
    row = _read(f)[0]
    assert row["body"] == body and row["message_id"] == "<4.JavaMail.evans@thyme>"
    assert row["label"] == "formal" and row["to"] == ""
    assert f.read_bytes().splitlines()[2] == before[2]        # a row with no address, byte for byte


def test_a_body_with_its_own_crlf_is_rewritten_byte_for_byte(tmp_path):
    # The real files end rows in \n but carry \r\n inside quoted bodies; reading
    # that as the row ending made the rewrite refuse the whole file.
    f = tmp_path / "f.csv"
    _write(f, [["a@enron.com", "", "x", "d", "<7@thyme>", "line one\r\nline two", "formal"]])
    before = f.read_bytes()
    pe.main([str(f)])
    assert f.read_bytes() == before.replace(b"a@enron.com", b"[EMAIL_0001]")


def test_check_counts_what_pt14_counts(tmp_path, capsys):
    f = tmp_path / "f.csv"
    _write(f, [["a@enron.com", "b@enron.com, a@enron.com", "x", "d", "<6.JavaMail.evans@thyme>", "y", "z"]])
    assert pe.main(["--check", str(f)]) == 1 and "2 unique" in capsys.readouterr().out
    pe.main([str(f)])
    assert pe.main(["--check", str(f)]) == 0


@pytest.mark.parametrize("path", sorted((ROOT / "data" / "processed").glob("*.csv")), ids=lambda p: p.name)
def test_processed_data_holds_no_email_addresses(path):
    # PT-14 found real Enron addresses in the tone CSVs; keep them out.
    rows, _ = pe.load(path)
    assert not pe.email_like(rows), f"{path.name} has email addresses - run pseudonymise_emails.py on it"
