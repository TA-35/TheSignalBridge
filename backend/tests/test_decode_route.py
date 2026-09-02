from app import create_app
from app.config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


def _client():
    return create_app(TestConfig).test_client()


def test_decode_returns_covered_and_missing_in_contract_shape():
    resp = _client().post("/api/decode", json={"message": "Send the invoice."})
    assert resp.status_code == 200
    body = resp.get_json()

    assert "task" in body["covered"]
    for key in ("time", "deadline", "for_whom"):
        assert body["elements"][key] == "Not specified"
        assert key in [m["field"] for m in body["missing"]]


def test_missing_entries_carry_a_prompt():
    resp = _client().post("/api/decode", json={"message": "Send the invoice."})
    for entry in resp.get_json()["missing"]:
        assert entry["prompt"], f"no prompt for {entry['field']}"


def test_elements_are_verbatim_substrings_of_the_message():
    message = "Please send the Q3 report for the client by next Tuesday at 3pm."
    body = _client().post("/api/decode", json={"message": message}).get_json()

    for key, value in body["elements"].items():
        if value != "Not specified":
            assert value in message, f"{key} value is not grounded in the message"


def test_spans_index_back_to_the_original_message():
    message = "Please send the Q3 report for the client by next Tuesday at 3pm."
    body = _client().post("/api/decode", json={"message": message}).get_json()

    for key, span in body["spans"].items():
        if span is not None:
            start, end = span
            assert message[start:end] == body["elements"][key]


def test_empty_message_returns_error_not_a_breakdown():
    resp = _client().post("/api/decode", json={"message": ""})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Please enter a message"


def test_meaningless_message_returns_same_error():
    resp = _client().post("/api/decode", json={"message": "!!! ### 123"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Please enter a message"


# Category enum from docs/api-contract.md - a value outside this set would
# silently break the patterns join, and null means "no flashcard".
CATEGORY_ENUM = {
    "Softened request",
    "Vague deadline",
    "Unassigned owner",
    "Feedback framing",
    "Unclear priority",
    "Undefined scope",
}


def test_task_is_a_clause_not_the_whole_message():
    # Regression: the task used to echo the entire sentence back, which
    # made the breakdown look like it had copied the user's input.
    message = "Please send the Q3 report for the client by next Tuesday at 3pm."
    task = _client().post("/api/decode", json={"message": message}).get_json()["elements"]["task"]

    assert task == "send the Q3 report"
    assert task != message
    # The other fields' text must not be duplicated inside the task.
    assert "next Tuesday" not in task
    assert "client" not in task
    assert "3pm" not in task


def test_category_is_returned_for_a_known_pattern():
    # Regression: category was hardcoded to None, so the frontend never
    # offered a flashcard (DecodeView gates on `if (result.category)`).
    body = _client().post(
        "/api/decode", json={"message": "Could you take a look at the deck before Friday?"}
    ).get_json()

    assert body["category"] == "Vague deadline"


def test_category_is_always_null_or_inside_the_enum():
    messages = [
        "No pressure, but can you loop in whoever owns the billing flow?",
        "Just a few small tweaks to the landing page.",
        "Send the invoice.",
    ]
    for message in messages:
        category = _client().post("/api/decode", json={"message": message}).get_json()["category"]
        assert category is None or category in CATEGORY_ENUM, f"{message} -> {category}"


SAMPLE = (
    "Hi,\n\nWhen you get a chance, could you take a look at the Q3 deck and "
    "tighten up the numbers section? Would be great to have it before the "
    "leadership sync.\n\nAlso, loop in whoever owns the pricing slide if "
    "that's easier.\n\nThanks!"
)


def test_every_ask_becomes_its_own_task():
    # The app's own sample contains three asks; the single-task view only
    # ever reported the first.
    tasks = _client().post("/api/decode", json={"message": SAMPLE}).get_json()["tasks"]

    assert len(tasks) == 3
    assert tasks[0]["text"] == "take a look at the Q3 deck"
    assert tasks[1]["text"] == "tighten up the numbers section"
    assert tasks[2]["text"].startswith("loop in whoever owns the pricing slide")


def test_task_text_is_verbatim_from_the_message():
    tasks = _client().post("/api/decode", json={"message": SAMPLE}).get_json()["tasks"]

    for task in tasks:
        start, end = task["span"]
        assert SAMPLE[start:end] == task["text"]


def test_each_task_carries_its_own_gaps():
    tasks = _client().post("/api/decode", json={"message": SAMPLE}).get_json()["tasks"]

    for task in tasks:
        gaps = {m["field"] for m in task["missing"]}
        for field in ("time", "deadline", "for_whom"):
            # A field is either reported on the task or listed as its gap,
            # never both and never neither.
            assert (task[field] == "Not specified") == (field in gaps)


def test_a_field_is_scoped_to_the_task_it_sits_in():
    message = "Please send the Q3 report for the client by Friday."
    tasks = _client().post("/api/decode", json={"message": message}).get_json()["tasks"]

    assert len(tasks) == 1
    assert tasks[0]["deadline"] == "Friday"
    assert tasks[0]["for_whom"] == "client"


def test_a_message_with_no_ask_has_no_tasks():
    body = _client().post(
        "/api/decode", json={"message": "Thanks for your help yesterday, really appreciate it."}
    ).get_json()

    assert body["tasks"] == []
    assert body["elements"]["task"] == "Not specified"


def test_elements_still_reports_the_first_task():
    body = _client().post("/api/decode", json={"message": SAMPLE}).get_json()

    # v1 contract preserved: `elements` is the single-task view.
    assert body["elements"]["task"] == body["tasks"][0]["text"]
