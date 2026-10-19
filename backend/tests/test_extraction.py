from app.services.extraction import extract_all, extract_fields, is_meaningless


def test_parses_message_with_all_four_fields_present():
    text = "Please send the Q3 report for the client by next Tuesday at 3pm."
    fields = extract_fields(text)

    assert fields["time"].specified is True
    assert fields["deadline"].specified is True
    assert fields["task_to_do"].specified is True
    assert fields["for_whom"].specified is True


def test_extracted_values_are_grounded_in_the_original_text():
    text = "Please send the Q3 report for the client by next Tuesday at 3pm."
    fields = extract_fields(text)

    for name, result in fields.items():
        if result.specified:
            start, end = result.span
            assert text[start:end] == result.value, f"{name} span does not match its value"


def test_missing_fields_are_marked_not_specified_not_guessed():
    text = "Send the invoice."
    fields = extract_fields(text)

    assert fields["task_to_do"].specified is True
    for name in ("time", "deadline", "for_whom"):
        assert fields[name].specified is False
        assert fields[name].value is None
        assert fields[name].span is None


def test_non_task_message_leaves_task_to_do_unspecified():
    # Regression guard: don't let the extractor invent a task from a
    # message that isn't actually asking for anything.
    text = "Thanks for your help yesterday, really appreciate it."
    fields = extract_fields(text)
    assert fields["task_to_do"].specified is False


def test_empty_input_is_meaningless():
    assert is_meaningless("") is True
    assert is_meaningless("   ") is True


def test_punctuation_only_input_is_meaningless():
    assert is_meaningless("!!! ### 123") is True


def test_real_message_is_not_meaningless():
    assert is_meaningless("Can you review the slides sometime this week?") is False


def test_for_whom_ignores_a_day_after_for():
    # "the slides for Friday" names when, not who. A real message showed
    # "For whom: Friday" on the page.
    fields = extract_fields("I have attached the slides for Friday. Send any questions by Monday.")
    assert fields["for_whom"].specified is False


def test_meeting_minutes_are_not_a_time():
    # spaCy tags "the minutes" as TIME; the task was then cut to "send me".
    fields, clauses = extract_all("Can you send me the minutes from Tuesday by 5pm tomorrow?")
    assert [c.value for c in clauses] == ["send me the minutes from Tuesday"]
    assert fields["deadline"].value == "5pm tomorrow"
    assert fields["time"].specified is False


def test_a_date_that_says_which_thing_does_not_cut_the_task():
    fields, clauses = extract_all("Could you send me the Q3 report from last week by Friday?")
    assert [c.value for c in clauses] == ["send me the Q3 report from last week"]
    assert fields["deadline"].value == "Friday"


def test_please_forward_is_an_ask():
    # spaCy tags "forward" after "Please" as an adverb, so no task was found.
    _, clauses = extract_all("Please forward the invoice from March to finance.")
    assert [c.value for c in clauses] == ["forward the invoice from March to finance"]


def test_an_ask_to_everyone_is_an_ask():
    _, clauses = extract_all("Hey all, so could everyone pack their desks by Tuesday afternoon?")
    assert [c.value for c in clauses] == ["pack their desks"]


def test_a_dangling_or_is_trimmed():
    # Two asks joined by "or": the first used to end "...address\nor".
    _, clauses = extract_all("Please mail me at the referenced address\nor call me during business hours.")
    assert clauses[0].value == "mail me at the referenced address"


def test_a_one_word_label_is_not_a_task():
    _, clauses = extract_all("Please only edit your own entries.\n\nLink -->\nhttp://example.com/db")
    assert [c.value for c in clauses] == ["edit your own entries"]


def test_for_whom_still_finds_a_person_after_a_day():
    fields = extract_fields("Prepare the deck for Friday for Priya.")
    assert fields["for_whom"].value == "Priya"
