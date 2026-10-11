"""Tests for applying reviewed gold-draft fixes."""
import json

import pytest

from Src.source.data_prep import gold_fixes as gf


def draft(i, **extra):
    return {"id": f"stanford_{i:05d}", "dataset": "stanford", "source": "Could you send it?",
            "meaning": {"ask": "Send it", "deadline": "", "urgency": "low", "tone": "polite", "implied": ""},
            "rewrite": "Please send it.", "notes": ["Made the ask direct."], "model": "teacher", **extra}


DRAFTS = [draft(1), draft(2), draft(3)]


def test_accepted_fixes_apply_rejected_ones_dont_and_every_row_is_checked():
    fixes = {"stanford_00001": {"status": "accept", "why": "x", "rewrite": "Could you send it, please?",
                                "notes": ["Kept your question; added please."], "meaning": {"urgency": "medium"}},
             "stanford_00002": {"status": "reject", "why": "x", "rewrite": "SHOULD NOT APPEAR"}}
    rows, counts = gf.apply(DRAFTS, fixes, "Anuvrat")
    assert counts == {"accepted": 1, "rejected": 1}
    assert [r["id"] for r in rows] == [d["id"] for d in DRAFTS]
    assert rows[0]["rewrite"] == "Could you send it, please?" and rows[0]["notes"] == ["Kept your question; added please."]
    assert rows[0]["meaning"] == {**DRAFTS[0]["meaning"], "urgency": "medium"}   # only the given field replaced
    assert rows[1]["rewrite"] == "Please send it."
    assert all(r["checked_by"] == "Anuvrat" and list(r)[-1] == "checked_by" for r in rows)
    assert DRAFTS[0]["rewrite"] == "Please send it."                            # inputs untouched


def test_refuses_while_any_fix_is_undecided():
    with pytest.raises(ValueError, match="stanford_00001: status is 'proposed'"):
        gf.apply(DRAFTS, {"stanford_00001": {"status": "proposed", "rewrite": "x"}}, "Anuvrat")


@pytest.mark.parametrize("fix, message", [
    ({"notes": ["one", "two", "three", "four"]}, "4 notes"),
    ({"notes": ["word " * 20]}, "under 20"),
    ({"rewrite": "  "}, "missing or empty rewrite"),
    ({"meaning": {"urgency": "urgent"}}, "not low/medium/high"),
    ({"meaning": {"askk": "typo"}}, "unknown meaning fields"),
])
def test_refuses_a_fix_that_would_break_the_draft(fix, message):
    with pytest.raises(ValueError, match=message):
        gf.apply(DRAFTS, {"stanford_00002": {"status": "accept", **fix}}, "Anuvrat")


def test_refuses_unknown_ids_and_a_missing_name():
    with pytest.raises(ValueError, match="no draft with this id"):
        gf.apply(DRAFTS, {"stanford_09999": {"status": "accept"}}, "Anuvrat")
    with pytest.raises(ValueError, match="checked_by is empty"):
        gf.apply(DRAFTS, {}, " ")


def test_main_writes_nothing_until_every_fix_is_decided(tmp_path):
    drafts = tmp_path / "stanford_gold_draft.jsonl"
    drafts.write_text("".join(json.dumps(d) + "\n" for d in DRAFTS))
    fixes = tmp_path / "stanford_gold_fixes.json"
    fixes.write_text(json.dumps({"stanford_00003": {"status": "proposed", "rewrite": "Send it now."}}))
    before = drafts.read_text()
    assert gf.main(["stanford", "--checked-by", "Yvonne", "--dir", str(tmp_path)]) == 1
    assert drafts.read_text() == before
    fixes.write_text(json.dumps({"stanford_00003": {"status": "accept", "rewrite": "Send it now."}}))
    assert gf.main(["stanford", "--checked-by", "Yvonne", "--dir", str(tmp_path)]) == 0
    rows = [json.loads(line) for line in drafts.read_text().splitlines()]
    assert rows[2]["rewrite"] == "Send it now." and {r["checked_by"] for r in rows} == {"Yvonne"}
