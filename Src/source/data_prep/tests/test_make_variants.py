"""Tests for the hedged / rough-notes variant maker. The teacher and the
classifiers are faked; entity checks use the real spaCy model."""
import json

import pytest

from Src.source.data_prep import make_variants as mv

pytest.importorskip("spacy")
try:
    mv.fp.nlp()
except OSError:
    pytest.skip("en_core_web_sm not installed", allow_module_level=True)

SIGNALS = [{"model": "tone", "label": "casual", "confidence": 0.9}]
ORIGINAL = "Can you send the Q3 report to Dana by Friday?"


def test_hedged_variant_must_keep_every_entity():
    good = "No rush, but if you get a chance could you maybe send the Q3 report to Dana by Friday?"
    assert mv.problem("hedges", ORIGINAL, good) is None
    assert mv.problem("hedges", ORIGINAL, "No rush, but could you maybe send the Q3 report to Dana sometime?") \
        == "dropped an entity"


def test_no_variant_may_add_an_entity():
    assert mv.problem("notes", ORIGINAL, "tell dana q3 report by friday 5pm") == "added an entity"
    assert mv.problem("hedges", ORIGINAL, "Hi Sam, no rush, but could you send the Q3 report to Dana by Friday?") \
        == "added an entity"


def test_notes_are_shorter_and_never_the_original():
    assert mv.problem("notes", ORIGINAL, "send q3 report to Dana by Friday") is None
    assert mv.problem("notes", ORIGINAL, ORIGINAL) == "unchanged"
    assert mv.problem("notes", ORIGINAL, ORIGINAL + " " + "so basically yeah " * 5) == "longer than the original"


def test_parse_takes_the_json_object_only():
    assert mv.parse('Sure! {"message": "tell dana q3", "style": "typed"}')["style"] == "typed"
    assert mv.parse("no json here") is None
    assert mv.parse('{"message": "  "}') is None


def test_hedges_and_notes_never_share_an_original():
    cands = {pool: [{"id": f"{pool}_{i:05d}"} for i in range(40)] for pool in mv.POOLS}
    hedges = {r["id"] for r in mv.pick(cands, "hedges", 40)}
    notes = {r["id"] for r in mv.pick(cands, "notes", 40)}
    assert len(hedges) == len(notes) == 40 and not hedges & notes


def _repo(tmp_path, n=6):
    gen = tmp_path / "data" / "generated"
    gen.mkdir(parents=True)
    for pool in mv.POOLS:
        rows = [{"id": f"{pool}_{i:05d}", "dataset": pool, "source": f"Can you send the report to Dana by Friday please {i}?",
                 "meaning": {"ask": "Send the report"}, "rewrite": "x", "notes": ["x"]} for i in range(n)]
        (gen / f"{pool}_gen.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


def test_run_writes_variants_with_signals_and_origin(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(mv.fp, "gold_index", lambda: (set(), []))
    reply = json.dumps({"message": "send report to Dana by Friday", "style": "typed"})
    counts = mv.run("notes", 4, root=root, workers=1, ask=lambda m: reply, signals=lambda t: SIGNALS)
    rows = [json.loads(l) for l in (root / "data/source/notes_source.jsonl").read_text().splitlines()]
    assert counts["written"] == 4 and len(rows) == 4
    assert {r["dataset"] for r in rows} == {"notes"} and all(r["signals"] == SIGNALS for r in rows)
    assert all(r["origin"].startswith(("enron_", "stanford_")) and r["style"] == "typed" for r in rows)
    assert [r["id"] for r in rows] == ["notes_00001", "notes_00002", "notes_00003", "notes_00004"]


def test_rerun_keeps_what_is_written_and_skips_rejects(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(mv.fp, "gold_index", lambda: (set(), []))
    good = json.dumps({"message": "send report to Dana by Friday"})
    mv.run("notes", 4, root=root, workers=1, ask=lambda m: good, signals=lambda t: SIGNALS)
    asked = []
    mv.run("notes", 4, root=root, workers=1, ask=lambda m: asked.append(1) or good, signals=lambda t: SIGNALS)
    assert asked == []
    bad = json.dumps({"message": "send report to Dana by Friday at 5pm"})       # adds a time
    counts = mv.run("hedges", 4, root=root, workers=1, ask=lambda m: bad, signals=lambda t: SIGNALS)
    assert counts == {"written": 0, "rejected": 4}
