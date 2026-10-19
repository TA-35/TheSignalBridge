"""Validator tests: the span check, the entity check, and degraded fallback."""
from __future__ import annotations

import pytest

from Src.source.pipeline.analysis import analyse
from Src.source.pipeline.validator import (
    check_entities,
    check_spans,
    resolve_span,
    salvage_response,
    templated_output,
    validate_response,
)

MESSAGE = "Could you send the report to the client by Friday? It's urgent."


@pytest.fixture(scope="module")
def analysis():
    return analyse(MESSAGE)


# --------------------------------------------------------------------------
# Span check
# --------------------------------------------------------------------------

def test_accepts_a_span_that_matches_the_source():
    start = MESSAGE.index("Friday")
    good = {"claims": [{"text": "Friday", "span": [start, start + 6]}]}
    assert check_spans(good, MESSAGE).ok


def test_rejects_a_span_whose_quoted_text_does_not_match():
    start = MESSAGE.index("Friday")
    bad = {"claims": [{"text": "Monday", "span": [start, start + 6]}]}
    result = check_spans(bad, MESSAGE)
    assert not result.ok
    assert "does not match" in result.failures[0]


def test_rejects_an_out_of_bounds_span():
    bad = {"claims": [{"text": "x", "span": [0, len(MESSAGE) + 50]}]}
    assert not check_spans(bad, MESSAGE).ok


@pytest.mark.parametrize("span", [None, [1], [1, 2, 3], "0,5", [1.5, 2.5], [True, False]])
def test_rejects_a_malformed_span(span):
    assert not check_spans({"claims": [{"text": "x", "span": span}]}, MESSAGE).ok


def test_finds_spans_nested_anywhere():
    start = MESSAGE.index("report")
    deep = {"a": {"b": [{"c": {"text": "Monday", "span": [start, start + 6]}}]}}
    result = check_spans(deep, MESSAGE)
    assert not result.ok
    assert "response.a.b[0].c" in result.failures[0]


def test_a_response_with_no_spans_passes_the_span_check():
    assert check_spans({"summary": "no citations here"}, MESSAGE).ok


# --------------------------------------------------------------------------
# Entity check - the case the brief calls out
# --------------------------------------------------------------------------

def test_rejects_a_date_the_input_does_not_contain():
    """The brief's named case: a fabricated date must be caught."""
    invented = {"summary": "They need the report by Tuesday."}
    result = check_entities(invented, MESSAGE)
    assert not result.ok
    assert any("DATE" in f for f in result.failures)


def test_accepts_a_date_the_input_does_contain():
    assert check_entities({"summary": "The deadline is Friday."}, MESSAGE).ok


@pytest.mark.parametrize("name", ["Sarah", "Dana", "Priya", "Aarav"])
def test_rejects_an_invented_person(name):
    """Names must be caught whether or not spaCy's NER recognises them.

    en_core_web_sm tags "Sarah" and "Dana" as PERSON but yields no entity at
    all for a bare "Priya", so the NER pass alone would let it through. The
    capitalised-word net is what makes this parametrisation pass.
    """
    result = check_entities({"summary": f"Ask {name} to send it."}, MESSAGE)
    assert not result.ok


def test_a_name_present_in_the_input_is_not_flagged():
    msg = "Could you ask Priya to send the report?"
    assert check_entities({"summary": "Priya needs to send it."}, msg).ok


def test_rejects_an_invented_number():
    result = check_entities({"summary": "There are 3 reports outstanding."}, MESSAGE)
    assert not result.ok


def test_number_words_and_digits_are_treated_as_the_same_fact():
    msg = "Please send 2 copies."
    assert check_entities({"summary": "Send two copies."}, msg).ok


def test_case_and_punctuation_do_not_count_as_invention():
    assert check_entities({"summary": "due FRIDAY!"}, MESSAGE).ok


def test_entity_check_ignores_text_inside_span_keys():
    assert check_entities({"claims": [{"span": [0, 5], "text": "Could"}]}, MESSAGE).ok


# --------------------------------------------------------------------------
# End to end: degraded output
# --------------------------------------------------------------------------

def test_invented_date_produces_degraded_output(analysis):
    """The end-to-end case the brief asks for explicitly."""
    invented = {"summary": "They need this by Tuesday.", "claims": []}
    out = validate_response(invented, MESSAGE, analysis)
    assert out["degraded"] is True
    assert any("DATE" in r for r in out["degraded_reason"])
    assert out["summary"] != invented["summary"]


def test_clean_response_passes_through_undegraded(analysis):
    start = MESSAGE.index("Friday")
    clean = {
        "summary": "A request with a Friday deadline.",
        "claims": [{"text": "Friday", "span": [start, start + 6]}],
    }
    out = validate_response(clean, MESSAGE, analysis)
    assert out["degraded"] is False
    assert out["summary"] == clean["summary"]


def test_bad_span_also_degrades(analysis):
    bad = {"claims": [{"text": "Monday", "span": [0, 6]}]}
    assert validate_response(bad, MESSAGE, analysis)["degraded"] is True


def test_non_object_response_degrades(analysis):
    assert validate_response("just a string", MESSAGE, analysis)["degraded"] is True
    assert validate_response(None, MESSAGE, analysis)["degraded"] is True


def test_degraded_output_quotes_only_the_original(analysis):
    """Every claim in the fallback must be verbatim from the message."""
    out = templated_output(analysis, ["test"])
    assert out["degraded"] is True
    assert out["claims"], "extractor found nothing to fall back on"
    for claim in out["claims"]:
        start, end = claim["span"]
        assert MESSAGE[start:end] == claim["text"]


def test_degraded_output_contains_no_invented_entities(analysis):
    """The fallback must itself pass the check that rejected the model."""
    out = templated_output(analysis, ["test"])
    assert check_entities(out, MESSAGE).ok


def test_failure_reasons_never_leak_the_message_body(analysis):
    secret = "Ship the Acme contract to Dana by Friday."
    secret_analysis = analyse(secret)
    bad = {"summary": "Send it by Tuesday.", "claims": [{"text": "Wrong", "span": [0, 4]}]}
    out = validate_response(bad, secret, secret_analysis)
    blob = " ".join(out["degraded_reason"])
    assert "Acme" not in blob
    assert "Dana" not in blob
    assert secret not in blob


# --------------------------------------------------------------------------
# Regression from the first real K3 run: "one" as a determiner
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "One thing is unclear.",
    "Send one copy.",
    "No one is named.",
    "This is one of several asks.",
])
def test_the_word_one_does_not_count_as_an_invented_number(text):
    """spaCy tags determiner "one" as CARDINAL. Rejecting on it degraded a
    real K3 response for ordinary English, and would degrade most answers."""
    assert check_entities({"summary": text}, MESSAGE).ok


@pytest.mark.parametrize("text", [
    "There are 3 reports.",
    "It asks for two things.",
    "Send 15 copies.",
])
def test_real_numbers_are_still_rejected(text):
    """The exemption must not open the door to actual fabricated quantities."""
    assert not check_entities({"summary": text}, MESSAGE).ok


# --------------------------------------------------------------------------
# Partial salvage: an unverifiable claim is not an invented fact
# --------------------------------------------------------------------------

def test_an_unresolvable_claim_is_dropped_and_the_rest_survive(analysis):
    """llama-3.2-11b reliably gives three or four good claims then fabricates
    one. Discarding all of them to punish the last degraded 4 runs in 6."""
    start = MESSAGE.index("Friday")
    response = {
        "summary": "A request with a Friday deadline.",
        "claims": [
            {"field": "deadline", "text": "Friday", "span_hint": start,
             "reading": "the deadline"},
            {"field": "priority", "text": "urgent", "span_hint": 56,
             "reading": "stated urgency"},
            {"field": "context", "text": "next quarter's roadmap",
             "span_hint": 10, "reading": "fabricated"},
        ],
        "unstated": [],
    }
    out = validate_response(response, MESSAGE, analysis)
    assert out["degraded"] is False, "good claims must survive"
    assert len(out["claims"]) == 2
    assert out["dropped_claims"] == 1
    for claim in out["claims"]:
        start, end = claim["span"]
        assert MESSAGE[start:end] == claim["text"]


def test_an_invented_entity_still_discards_everything(analysis):
    """Different failure, different response: a fact from nowhere means the
    whole reading is suspect, not just one claim."""
    start = MESSAGE.index("Friday")
    response = {
        "summary": "They need it by Tuesday.",
        "claims": [{"field": "deadline", "text": "Friday", "span_hint": start,
                    "reading": "deadline"}],
        "unstated": [],
    }
    out = validate_response(response, MESSAGE, analysis)
    assert out["degraded"] is True
    assert any("DATE" in r for r in out["degraded_reason"])


def test_when_no_claim_survives_the_response_degrades(analysis):
    response = {
        "summary": "ok",
        "claims": [{"field": "deadline", "text": "not in the message at all",
                    "span_hint": 0, "reading": "x"}],
        "unstated": [],
    }
    out = validate_response(response, MESSAGE, analysis)
    assert out["degraded"] is True


def test_a_fully_clean_response_reports_no_drops(analysis):
    start = MESSAGE.index("Friday")
    out = validate_response({
        "summary": "ok",
        "claims": [{"field": "deadline", "text": "Friday", "span_hint": start,
                    "reading": "deadline"}],
        "unstated": [],
    }, MESSAGE, analysis)
    assert out["degraded"] is False
    assert "dropped_claims" not in out


# --------------------------------------------------------------------------
# What the entity check covers, and deliberately does not
# --------------------------------------------------------------------------

def test_a_fabricated_date_in_the_summary_is_still_caught():
    """The case the whole check exists for. Unchanged by the scoping."""
    assert not check_entities({"summary": "They need it by Tuesday."}, MESSAGE).ok


def test_interpretive_language_in_a_reading_is_not_an_invented_fact():
    """A reading reasons about ambiguity; that is what it is for. 'the
    business day' is not a claim the message said so - it degraded a real
    response once the prompt started asking for interpretation."""
    assert check_entities({
        "summary": "A request with a deadline.",
        "claims": [{"field": "deadline", "text": "Friday", "span": [43, 49],
                    "reading": "Friday is stated but not a time - if they mean "
                               "close of business day you have until 5."}],
    }, MESSAGE).ok


def test_hedging_about_time_and_quantity_is_allowed_in_questions():
    """`unstated` lists what the message does NOT say, so flagging it for
    containing absent dates or counts inverts its purpose. 'the only one' was
    rejected once as an invented CARDINAL."""
    assert check_entities({
        "summary": "A request.",
        "unstated": ["Is this the only ask, or is more coming?",
                     "Do they mean Tuesday or the end of the week?"],
    }, MESSAGE).ok


def test_an_invented_name_in_a_question_is_still_rejected():
    """Exempting interpretive fields entirely was too broad. A live run on a
    message containing no names produced 'is Sarah the only one?' - a
    fabricated colleague shown to the reader as though the message named them.

    Hedging about time is interpretation. Inventing a person is not: there is
    nothing vague about whether a name was written."""
    result = check_entities({
        "summary": "A request.",
        "unstated": ["Who else is expecting this - is Sarah the only one?"],
    }, MESSAGE)
    assert not result.ok
    assert any("PERSON" in f for f in result.failures)


def test_an_invented_name_in_a_reading_is_rejected():
    result = check_entities({
        "summary": "A request.",
        "claims": [{"field": "deadline", "text": "Friday", "span": [43, 49],
                    "reading": "This assumes Priya has already seen it."}],
    }, MESSAGE)
    assert not result.ok


@pytest.mark.parametrize("question,caught", [
    ("Is Priya the only one who needs this?", True),   # mid-sentence, NER misses
    ("Ask Sarah whether she has it.", True),           # mid-sentence, NER catches
    ("Sarah will need this first.", True),             # sentence start, NER catches
    ("Priya will need this first.", False),            # sentence start, NER misses
])
def test_the_limit_of_name_detection_is_known(question, caught):
    """Maps exactly where the two passes stop, rather than claiming they are
    exhaustive.

    The capitalised-word net skips sentence-initial tokens - it has to, or
    every sentence opener would be flagged - so a name spaCy does not
    recognise AND that starts a sentence escapes both passes. Measured on
    en_core_web_sm: 'Sarah' is tagged PERSON and caught anywhere; 'Priya' is
    not tagged at all and is caught only mid-sentence.

    The residual risk is narrow and one-directional: a fabricated name can
    only slip through in that one position. Closing it would mean flagging
    every capitalised word at the start of every sentence, which would degrade
    almost every response.
    """
    result = check_entities({"summary": "A request.", "unstated": [question]},
                            MESSAGE)
    assert (not result.ok) is caught


def test_a_name_that_is_in_the_message_is_fine_anywhere():
    msg = "Hi Sarah, could you send the report by Friday?"
    assert check_entities({
        "summary": "A request to Sarah.",
        "unstated": ["Is Sarah the only person who needs to act?"],
    }, msg).ok


def test_a_quote_is_not_re_checked_for_entities():
    """claims[].text is proven verbatim by span resolution; re-checking it
    can only produce false positives."""
    start = MESSAGE.index("Friday")
    assert check_entities({
        "summary": "ok",
        "claims": [{"field": "deadline", "text": "Friday", "span": [start, start + 6]}],
    }, MESSAGE).ok


# --------------------------------------------------------------------------
# Model-decided gaps
#
# `missing` drives the checkbox panel, which is the one part of the page the
# user acts on. A gap has no span by definition - it is the absence of text -
# so the span check cannot protect it and these rules do instead.
# --------------------------------------------------------------------------

def test_a_gap_question_may_hedge_about_what_the_message_left_vague(analysis):
    """Same reasoning as `unstated`: a question about an absent deadline will
    mention times the message never stated. That is the point of it."""
    out = validate_response({
        "summary": "A request.",
        "claims": [],
        "unstated": [],
        "missing": [{"field": "deadline",
                     "question": "Is Friday end of day, or before your 9am?"}],
    }, MESSAGE, analysis)
    assert not out["degraded"], out.get("degraded_reason")
    assert out["missing"] == [
        {"field": "deadline", "question": "Is Friday end of day, or before your 9am?"}
    ]


@pytest.mark.parametrize("name", ["Sarah", "Priya"])
def test_an_invented_name_in_a_gap_question_is_rejected(analysis, name):
    """The narrower check has to reach `question` too. Without it the panel
    the user reads most closely would be the one place a fabricated colleague
    could still appear.

    Both names are caught, by different halves of the check: en_core_web_sm
    tags Sarah PERSON and does not know Priya at all, which the capitalised
    word fallback catches instead. Asserting on the PERSON label alone passed
    for Sarah and failed for Priya - the rejection is what matters, not which
    mechanism produced it."""
    out = validate_response({
        "summary": "A request.",
        "claims": [],
        "unstated": [],
        "missing": [{"field": "responsible_person",
                     "question": f"Should {name} handle this, or you?"}],
    }, MESSAGE, analysis)
    assert out["degraded"]
    assert any(name in r for r in out["degraded_reason"])


def test_the_limit_of_name_detection_in_a_gap_question_is_known(analysis):
    """A name spaCy does not know, placed first in the sentence, is
    indistinguishable from an ordinary capitalised word and gets through.

    Recorded rather than fixed: the fallback cannot treat every
    sentence-initial capital as a name without rejecting "Do you need this
    Friday?" and most other legitimate questions. The narrower guarantee -
    a known name anywhere, an unknown name anywhere but sentence-initial -
    is the one actually being made, and it should fail loudly here the day
    it changes."""
    out = validate_response({
        "summary": "A request.",
        "claims": [],
        "unstated": [],
        "missing": [{"field": "responsible_person",
                     "question": "Priya should handle this, or you?"}],
    }, MESSAGE, analysis)
    assert not out["degraded"], "behaviour changed - tighten the docs, not just this test"


def test_a_field_cannot_be_both_claimed_and_missing(analysis):
    """A page listing the deadline as found, directly above a checkbox asking
    for the deadline, reads as broken. Claims win - they carry a span."""
    start = MESSAGE.index("Friday")
    out = validate_response({
        "summary": "A request.",
        "claims": [{"field": "deadline", "text": "Friday", "span_hint": start,
                    "reading": "Friday is stated, but no time of day is."}],
        "unstated": [],
        "missing": [{"field": "deadline", "question": "When do you need this?"},
                    {"field": "priority", "question": "How urgent is this?"}],
    }, MESSAGE, analysis)
    assert not out["degraded"], out.get("degraded_reason")
    assert [g["field"] for g in out["missing"]] == ["priority"]


def test_a_dropped_claim_reopens_its_gap(analysis):
    """The exclusivity check runs against surviving claims, not the model's
    original list. A deadline claim that fails verification leaves the
    deadline genuinely unsettled, so the checkbox has to come back - keying
    off the unverified claim would silently swallow it.
    Needs a claim that survives alongside the one that fails: when nothing
    resolves there is no partial answer and the whole response falls back to
    the extractor, which is a different path with its own gap list."""
    start = MESSAGE.index("urgent")
    out = validate_response({
        "summary": "A request.",
        "claims": [
            {"field": "priority", "text": "urgent", "span_hint": start,
             "reading": "Stated outright rather than implied."},
            {"field": "deadline", "text": "next Tuesday", "span_hint": 0,
             "reading": "A date that is not in the message at all."},
        ],
        "unstated": [],
        "missing": [{"field": "deadline", "question": "When do you need this?"}],
    }, MESSAGE, analysis)
    assert not out["degraded"], out.get("degraded_reason")
    assert [c["field"] for c in out["claims"]] == ["priority"]
    assert [g["field"] for g in out["missing"]] == ["deadline"]


def test_the_degraded_fallback_answers_in_the_same_shape(analysis):
    """Two shapes for one panel means the frontend needs two renderers, and
    whichever one is exercised less is the one that breaks."""
    out = templated_output(analysis, ["forced"])
    assert out["degraded"]
    for gap in out["missing"]:
        assert set(gap) == {"field", "question"}
        assert gap["question"].strip()


# --------------------------------------------------------------------------
# Faithful quotes that are not character-exact (measured on GPT-OSS)
# --------------------------------------------------------------------------

def test_a_line_break_typed_as_a_space_still_resolves():
    """Enron emails are hard-wrapped; the model quotes the sentence whole."""
    msg = "Could you send the\nreport to Dana by Friday?"
    span = resolve_span(msg, "send the report to Dana", hint=10)
    assert span is not None
    assert msg[span[0]:span[1]] == "send the\nreport to Dana"


def test_a_curly_apostrophe_still_resolves():
    span = resolve_span(MESSAGE, "It\N{RIGHT SINGLE QUOTATION MARK}s urgent.", hint=50)
    assert MESSAGE[span[0]:span[1]] == "It's urgent."


def test_a_capital_added_at_the_start_still_resolves():
    msg = "thanks. please send the report by Friday."
    span = resolve_span(msg, "Please send the report", hint=8)
    assert msg[span[0]:span[1]] == "please send the report"


def test_a_paraphrase_still_does_not_resolve():
    assert resolve_span(MESSAGE, "send me the report", hint=0) is None


def test_the_reader_is_shown_the_message_text_not_the_models_copy(analysis):
    out = validate_response({
        "summary": "A request with a deadline.",
        "claims": [{"field": "priority", "text": "It\N{RIGHT SINGLE QUOTATION MARK}s urgent", "span_hint": 50,
                    "reading": "they say it is urgent"}],
        "unstated": [],
    }, MESSAGE, analysis)
    assert out["degraded"] is False
    assert out["claims"][0]["text"] == "It's urgent"


# --------------------------------------------------------------------------
# The same fact written another way is not an invented one
# --------------------------------------------------------------------------

def test_a_non_breaking_hyphen_is_not_a_company(analysis):
    """GPT-OSS writes U+2011 in compounds; spaCy took "follow-up", written
    with it, for an ORG."""
    start = MESSAGE.index("Friday")
    out = validate_response({
        "summary": "A request with a Friday deadline.",
        "claims": [{"field": "deadline", "text": "Friday", "span_hint": start,
                    "reading": "a follow\N{NON-BREAKING HYPHEN}up may be needed"}],
        "unstated": ["Is a real\N{NON-BREAKING HYPHEN}name sign-off needed?"],
    }, MESSAGE, analysis)
    assert out["degraded"] is False
    assert out["claims"][0]["reading"] == "a follow-up may be needed"


def test_a_possessive_is_the_same_person():
    msg = "Please ask Makayla Bean to sign the form."
    assert check_entities({"summary": "Makayla Bean\N{RIGHT SINGLE QUOTATION MARK}s signature is needed."}, msg).ok


@pytest.mark.parametrize("msg, summary", [
    ("The call is at 1:00 p.m. on Friday.", "A call at 1 p.m. on Friday."),
    # spaCy takes "around 4 pm" as the TIME in this phrasing, as it did in
    # the real answer that was lost.
    ("Call me at 4pm.", "Results are expected around 4 pm."),
])
def test_the_same_time_written_differently_is_not_invented(msg, summary):
    assert check_entities({"summary": summary}, msg).ok


def test_a_misspelt_deadline_word_is_still_the_same_word():
    """An Enron email said "tommorow"; every answer that said "tomorrow" failed."""
    msg = "Can you get me the figures tommorow?"
    assert check_entities({"summary": "They want the figures tomorrow."}, msg).ok
    assert not check_entities({"summary": "They want the figures today."}, msg).ok


def test_a_different_time_is_still_invented():
    assert not check_entities({"summary": "A call around 5 pm."}, "Call me at 4pm.").ok


# --------------------------------------------------------------------------
# Salvage: the last resort after repairs, keeping only what holds up alone
# --------------------------------------------------------------------------

def test_salvage_keeps_the_verified_parts():
    start = MESSAGE.index("Friday")
    out = salvage_response({
        "summary": "They need it by Tuesday.",
        "claims": [{"field": "deadline", "text": "Friday", "span_hint": start,
                    "reading": "the day it is due"}],
        "unstated": ["Who is the client?"],
        "missing": [],
    }, MESSAGE)
    assert out["degraded"] is False and out["partial"] is True
    assert out["summary"] == "", "the summary held the invented date"
    assert [c["text"] for c in out["claims"]] == ["Friday"]
    assert out["unstated"] == ["Who is the client?"]
    assert any("Tuesday" in r for r in out["dropped_reason"])


def test_salvage_cuts_an_invented_date_wherever_it_appears():
    """Readings are not normally checked for dates. Once the answer has been
    caught inventing one, every part is held to the summary's standard."""
    start = MESSAGE.index("Friday")
    out = salvage_response({
        "summary": "They need it by Tuesday.",
        "claims": [
            {"field": "deadline", "text": "Friday", "span_hint": start,
             "reading": "really means Tuesday"},
            {"field": "priority", "text": "urgent", "span_hint": 56,
             "reading": "they say it is urgent"},
        ],
        "unstated": ["Can it wait until Tuesday?"],
        "missing": [{"field": "responsible_person", "question": "Is Tuesday fine?"}],
    }, MESSAGE)
    shown = [out["summary"], *out["unstated"],
             *(c["reading"] for c in out["claims"]), *(g["question"] for g in out["missing"])]
    assert not any("Tuesday" in text for text in shown)
    assert [c["field"] for c in out["claims"]] == ["priority"]
    assert out["dropped_claims"] == 1


def test_salvage_gives_up_when_nothing_holds_up():
    assert salvage_response({
        "summary": "They need it by Tuesday.",
        "claims": [{"field": "deadline", "text": "not in the message", "span_hint": 0,
                    "reading": "x"}],
        "unstated": [],
        "missing": [],
    }, MESSAGE) is None
