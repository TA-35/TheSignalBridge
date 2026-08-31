from app.services.extraction import extract_fields, is_meaningless


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
