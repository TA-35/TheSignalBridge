"""Grounding check tests. Entity checks use the real spaCy model; NLI is faked
except in the one test that loads the real cross-encoder."""
from __future__ import annotations

import pytest

from Src.source.pipeline import grounding as g

pytest.importorskip("spacy")
try:
    g.fp.nlp()
except OSError:
    pytest.skip("en_core_web_sm not installed", allow_module_level=True)

SOURCE = "Hi Dana, no rush but could you check the Q3 numbers before Thursday's meeting? Thanks!"
CLASSES = {g.DROPPED, g.ADDED, g.CONTRADICTION, g.UNAVAILABLE}


@pytest.fixture
def nli(monkeypatch):
    """Fake NLI: records each call, answers `verdict`."""
    calls = []

    def fake(source, rewrite):
        calls.append((source, rewrite))
        return fake.verdict

    fake.verdict = False
    monkeypatch.setattr(g, "contradicts", fake)
    fake.calls = calls
    return fake


def test_faithful_rewrite_passes(nli):
    out = g.check(SOURCE, "Hi Dana, could you please check the Q3 numbers before Thursday's meeting? Thanks!")
    assert out.ok and out.reasons == ()
    assert out.checks() == {"entities_kept": True, "nothing_added": True, "no_contradiction": True}


def test_unchanged_message_passes(nli):
    assert g.check(SOURCE, SOURCE).ok


def test_dropped_name_fails_and_skips_nli(nli):
    out = g.check(SOURCE, "Could you please check the Q3 numbers before Thursday's meeting?")
    assert out.reasons == (g.DROPPED,) and not out.entities_kept
    assert out.no_contradiction is None and nli.calls == []


def test_added_date_fails(nli):
    out = g.check(SOURCE, "Hi Dana, could you check the Q3 numbers by Wednesday, before Thursday's meeting?")
    assert out.reasons == (g.ADDED,) and not out.nothing_added


def test_dropped_and_added_both_reported(nli):
    out = g.check(SOURCE, "Hi Dana, could you check the Q4 numbers before Thursday's meeting?")
    assert set(out.reasons) == {g.DROPPED, g.ADDED}


def test_contradiction_fails(nli):
    nli.verdict = True
    out = g.check(SOURCE, "Hi Dana, there's no need to check the Q3 numbers before Thursday's meeting.")
    assert out.reasons == (g.CONTRADICTION,) and out.no_contradiction is False


def test_placeholders_count_as_entities(nli):
    src = "Can you call me on [PHONE_REDACTED] about the doc at [URL]?"
    assert g.check(src, "Could you call me on [PHONE_REDACTED] about the doc at [URL]?").ok
    assert g.check(src, "Could you call me about the doc at [URL]?").reasons == (g.DROPPED,)


def test_entity_closing_a_sentence_is_kept(nli):
    # From the teacher bake-off. Needs the filter fix (fix/filter-false-rejects):
    # before it, "month." at the end of a line read as "end of month" dropped.
    src = "remind the team timesheets are due end of month and also the new parking rules start monday"
    rewrite = ("Hi all, two reminders:\n- Timesheets are due at the end of the month.\n"
               "- The new parking rules start Monday.")
    assert g.check(src, rewrite).ok


def test_casual_shorthand_rewrite_passes(nli):
    # Withheld on the live site: "b4" read as the number 4.
    src = "hey can u check the budget numbers b4 thursday, the client wants them early if possible"
    assert g.check(src, "Hey, can you check the budget numbers before Thursday? "
                        "The client wants them early if possible.").ok


def test_a_broken_check_fails_closed(nli, monkeypatch):
    def broken(record):
        raise RuntimeError("spaCy fell over")

    monkeypatch.setattr(g.fp, "check_dropped", broken)
    out = g.check(SOURCE, SOURCE)
    assert not out.ok and out.reasons == (g.UNAVAILABLE,)


def test_reasons_are_class_names_never_message_text(nli):
    rewrites = [SOURCE, "Could you check it?", "Hi Dana, check the Q4 numbers by Friday."]
    for rewrite in rewrites:
        assert set(g.check(SOURCE, rewrite).reasons) <= CLASSES


def test_real_nli_catches_a_flipped_answer():
    pytest.importorskip("sentence_transformers")
    try:
        g.warm_up()
    except Exception as exc:  # noqa: BLE001 - no model download available here
        pytest.skip(f"NLI model unavailable: {type(exc).__name__}")
    assert g._nli_model()[0].device.type in ("cpu", "cuda")      # never MPS, see _nli_model
    assert g.contradicts("I can come to the lunch on Friday.", "I can't come to the lunch on Friday.")
    assert g.contradicts("Send the report by Monday.", "Send the report by Tuesday.")
    assert not g.contradicts(SOURCE, "Hi Dana, could you please check the Q3 numbers before Thursday's meeting?")
