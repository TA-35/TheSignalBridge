"""Expand the reviewed Pattern Library from 25 to 60 cards.

Run from the Library_dataset directory after the original 25-card notebook cells.
The original records and IDs remain unchanged. Provenance metadata is used only
for the review preview and is not exported into the application JSON schema.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "library_dataset.json"
PREVIEW_PATH = ROOT / "library_dataset_preview.md"

CATEGORIES = [
    "Softened request",
    "Vague deadline",
    "Unassigned owner",
    "Unclear priority",
    "Undefined scope",
    "Feedback framing",
]
PUBLIC_FIELDS = ("id", "name", "category", "implies", "why_misread")


ADDITIONAL_CARDS = [
    # A6-A10: manually selected from the screened Stanford candidate pool.
    {
        "id": 26,
        "temp_id": "A6",
        "source": "real-corpus-derived",
        "source_id": "2353305",
        "source_score": 2.1714898253294734,
        "name": "Could you please do the math of whether it's useful or not?",
        "category": "Softened request",
        "implies": "Often, this signals they want a concrete calculation before deciding whether the idea is worthwhile.",
        "why_misread": "It's easy to read this as a general opinion question. The useful response is likely the actual calculation, not only a recommendation.",
    },
    {
        "id": 27,
        "temp_id": "A7",
        "source": "real-corpus-derived",
        "source_id": "2064",
        "source_score": 2.0310240163828164,
        "name": "Can you elaborate on the idea with the tagged PDFs?",
        "category": "Softened request",
        "implies": "This usually means they need more detail about how the idea would work before they can evaluate or use it.",
        "why_misread": "You might take ‘elaborate’ as an invitation to add background. They are likely asking for the practical mechanism or steps.",
    },
    {
        "id": 28,
        "temp_id": "A8",
        "source": "real-corpus-derived",
        "source_id": "2573674",
        "source_score": 1.805014096116688,
        "name": "Could you tell us what your thought process has been on this problem so far?",
        "category": "Softened request",
        "implies": "Often, this signals they need to see the reasoning already attempted, not just the final question.",
        "why_misread": "It's easy to read this as conversational curiosity. The earlier reasoning will probably determine what guidance is useful next.",
    },
    {
        "id": 29,
        "temp_id": "A9",
        "source": "real-corpus-derived",
        "source_id": "186097",
        "source_score": 1.8085395665268185,
        "name": "Could you make sure you move them from ‘To do’ to ‘Done’ when you finish?",
        "category": "Softened request",
        "implies": "This usually means updating the status is part of completing the task, rather than an optional administrative step.",
        "why_misread": "You might focus on finishing the work itself. The sender is also asking for the tracking record to be updated.",
    },
    {
        "id": 30,
        "temp_id": "A10",
        "source": "real-corpus-derived",
        "source_id": "358525",
        "source_score": 1.7550265050252072,
        "name": "Could you please review my replies and let me know if you're satisfied?",
        "category": "Softened request",
        "implies": "There's likely a concrete follow-up review needed. They want confirmation that the replies address the earlier concerns.",
        "why_misread": "It's easy to read this as a general invitation to comment. The requested outcome is likely approval or a clear list of remaining issues.",
    },

    # B21-B26: Vague deadline.
    {
        "id": 31,
        "temp_id": "B21",
        "source": "hand-designed",
        "name": "Could you send this over when you get a chance?",
        "category": "Vague deadline",
        "implies": "This usually means they expect it reasonably soon, although no specific delivery time has been agreed.",
        "why_misread": "You might take ‘when you get a chance’ as completely open-ended. The sender may still expect progress within the current work cycle.",
    },
    {
        "id": 32,
        "temp_id": "B22",
        "source": "hand-designed",
        "name": "Let's have a first version ready around the middle of next week.",
        "category": "Vague deadline",
        "implies": "There's likely a real target next week, but the exact day and time still need to be confirmed.",
        "why_misread": "It's easy to treat ‘around the middle’ as a usable deadline. Different people may interpret it as Tuesday, Wednesday, or Thursday.",
    },
    {
        "id": 33,
        "temp_id": "B23",
        "source": "hand-designed",
        "name": "It would be good to finish this ahead of the client meeting.",
        "category": "Vague deadline",
        "implies": "Often, this signals the work must be finished early enough for someone to review it before the meeting.",
        "why_misread": "You might read ‘ahead of’ as any time before the meeting. The sender may be assuming an unstated review buffer.",
    },
    {
        "id": 34,
        "temp_id": "B24",
        "source": "hand-designed",
        "name": "Can we get this moving in the next few days?",
        "category": "Vague deadline",
        "implies": "This usually means visible progress is expected soon, but it does not define what progress or which day.",
        "why_misread": "It's easy to interpret this as a flexible suggestion. The sender may expect a concrete start or update within a much narrower window.",
    },
    {
        "id": 35,
        "temp_id": "B25",
        "source": "hand-designed",
        "name": "Please make sure this is sorted before things get busy.",
        "category": "Vague deadline",
        "implies": "There's likely a deadline tied to an upcoming busy period, but that point has not been named.",
        "why_misread": "You might understand the urgency without knowing the date. ‘Before things get busy’ depends on context that the message does not supply.",
    },
    {
        "id": 36,
        "temp_id": "B26",
        "source": "hand-designed",
        "name": "We should probably close this out sooner rather than later.",
        "category": "Vague deadline",
        "implies": "Often, this signals moderate urgency and a preference to finish before other work intervenes.",
        "why_misread": "It's easy to recognize the urgency but still schedule it differently. The phrase provides no shared date for deciding what ‘sooner’ means.",
    },

    # B27-B32: Unassigned owner.
    {
        "id": 37,
        "temp_id": "B27",
        "source": "hand-designed",
        "name": "Someone needs to confirm the final numbers.",
        "category": "Unassigned owner",
        "implies": "This means a specific verification task is outstanding, but no person has been made responsible for completing it.",
        "why_misread": "It's easy to treat this as a general team reminder. Without a named owner, everyone may assume someone else will handle it.",
    },
    {
        "id": 38,
        "temp_id": "B28",
        "source": "hand-designed",
        "name": "Can we make sure the slides are updated before the meeting?",
        "category": "Unassigned owner",
        "implies": "This usually means the slide update must be completed, but ‘we’ does not identify who will do it.",
        "why_misread": "You might read this as shared responsibility. In practice, the task still needs one person to take ownership.",
    },
    {
        "id": 39,
        "temp_id": "B29",
        "source": "hand-designed",
        "name": "The client is still waiting for a response.",
        "category": "Unassigned owner",
        "implies": "Often, this signals that someone needs to reply promptly, even though the message does not assign that action.",
        "why_misread": "It's easy to read this only as a status update. The missing owner makes the implied follow-up easy to overlook.",
    },
    {
        "id": 40,
        "temp_id": "B30",
        "source": "hand-designed",
        "name": "There are a few action items left from yesterday's meeting.",
        "category": "Unassigned owner",
        "implies": "This usually means the remaining tasks need to be allocated and completed, not merely recorded.",
        "why_misread": "You might take this as meeting context rather than a request. No names are attached, so responsibility remains unclear.",
    },
    {
        "id": 41,
        "temp_id": "B31",
        "source": "hand-designed",
        "name": "The final document needs one more check.",
        "category": "Unassigned owner",
        "implies": "There's a clear review task before the document is final, but the reviewer has not been identified.",
        "why_misread": "It's easy to read this as information about the document's status. The sentence does not say who should perform the check.",
    },
    {
        "id": 42,
        "temp_id": "B32",
        "source": "hand-designed",
        "name": "We should follow up with the supplier about the delay.",
        "category": "Unassigned owner",
        "implies": "Often, this signals a concrete follow-up task, but the collective ‘we’ leaves individual responsibility unresolved.",
        "why_misread": "You might assume the group will coordinate it naturally. Without an assigned owner, the supplier may receive no response.",
    },

    # B33-B38: Unclear priority.
    {
        "id": 43,
        "temp_id": "B33",
        "source": "hand-designed",
        "name": "This isn't urgent, but I'd like to keep it moving.",
        "category": "Unclear priority",
        "implies": "This usually means the task should continue progressing, but its position relative to other work remains unclear.",
        "why_misread": "It's easy to focus on ‘isn't urgent’ and defer it. The second half signals that indefinite delay is not intended.",
    },
    {
        "id": 44,
        "temp_id": "B34",
        "source": "hand-designed",
        "name": "Please fit this in when you can.",
        "category": "Unclear priority",
        "implies": "There's a real task to schedule, but the message gives no rule for placing it among competing work.",
        "why_misread": "You might treat it as optional until spare time appears. The sender may expect it to receive a deliberate place in the schedule.",
    },
    {
        "id": 45,
        "temp_id": "B35",
        "source": "hand-designed",
        "name": "It would be good to address this before it becomes a problem.",
        "category": "Unclear priority",
        "implies": "Often, this signals preventive work that matters, although the current level of risk and priority are not stated.",
        "why_misread": "It's easy to deprioritize a problem that has not happened yet. The message gives no threshold for when action becomes important.",
    },
    {
        "id": 46,
        "temp_id": "B36",
        "source": "hand-designed",
        "name": "This should be near the top of the list.",
        "category": "Unclear priority",
        "implies": "This usually means the task is important, but ‘near the top’ does not establish an exact ranking.",
        "why_misread": "You might understand that it matters while still ordering it differently. The message does not identify what may remain ahead of it.",
    },
    {
        "id": 47,
        "temp_id": "B37",
        "source": "hand-designed",
        "name": "Focus on this if nothing more pressing comes up.",
        "category": "Unclear priority",
        "implies": "There's an intended focus task, but its priority changes according to an undefined idea of more pressing work.",
        "why_misread": "It's easy for almost any new request to seem more pressing. Without a comparison rule, this task can keep moving down the list.",
    },
    {
        "id": 48,
        "temp_id": "B38",
        "source": "hand-designed",
        "name": "We don't need it today, but I wouldn't leave it too long.",
        "category": "Unclear priority",
        "implies": "Often, this signals the task is below today's work but should not fall into the indefinite backlog.",
        "why_misread": "You might hear only that it is not needed today. The message does not say which upcoming tasks it should outrank.",
    },

    # B39-B44: Undefined scope.
    {
        "id": 49,
        "temp_id": "B39",
        "source": "hand-designed",
        "name": "Can you make the presentation more engaging?",
        "category": "Undefined scope",
        "implies": "This usually means some aspect of the presentation should change, but the desired audience response and acceptable changes are unspecified.",
        "why_misread": "It's easy to interpret ‘engaging’ through personal preference. The sender may mean the story, visuals, examples, delivery, or all four.",
    },
    {
        "id": 50,
        "temp_id": "B40",
        "source": "hand-designed",
        "name": "Please tidy up the data before we share it.",
        "category": "Undefined scope",
        "implies": "There's a data-cleaning task, but ‘tidy up’ does not define which errors, fields, or formatting must be addressed.",
        "why_misread": "You might make cosmetic changes while the sender expects missing values, duplicates, or inconsistent labels to be resolved.",
    },
    {
        "id": 51,
        "temp_id": "B41",
        "source": "hand-designed",
        "name": "Could you simplify the registration process?",
        "category": "Undefined scope",
        "implies": "Often, this signals that users face friction, but it does not identify which steps or success criteria define a simpler process.",
        "why_misread": "It's easy to assume the whole flow is open for redesign. The concern may involve only one form, instruction, or approval step.",
    },
    {
        "id": 52,
        "temp_id": "B42",
        "source": "hand-designed",
        "name": "Let's improve the wording on the homepage.",
        "category": "Undefined scope",
        "implies": "This usually means some homepage copy needs revision, but the affected sections, audience, and intended outcome are not defined.",
        "why_misread": "You might revise every section or only correct grammar. The message does not establish the size or purpose of the change.",
    },
    {
        "id": 53,
        "temp_id": "B43",
        "source": "hand-designed",
        "name": "Can you address the issues in the latest version?",
        "category": "Undefined scope",
        "implies": "There's a set of expected fixes, but the message does not identify which issues are included or what completion means.",
        "why_misread": "It's easy to assume both sides share the same issue list. Different understandings can produce very different amounts of work.",
    },
    {
        "id": 54,
        "temp_id": "B44",
        "source": "hand-designed",
        "name": "The final report could use a little more detail.",
        "category": "Undefined scope",
        "implies": "Often, this signals that important information is missing, but neither the sections nor the required level of detail are specified.",
        "why_misread": "You might add a few sentences while the sender expects new evidence, analysis, or explanation across several sections.",
    },

    # B45-B50: Feedback framing.
    {
        "id": 55,
        "temp_id": "B45",
        "source": "hand-designed",
        "name": "Really strong start. I just have a few thoughts on the structure.",
        "category": "Feedback framing",
        "implies": "This usually means the overall direction is positive, while the structural comments still require careful attention.",
        "why_misread": "It's easy to focus on the praise and treat the thoughts as optional. The actionable feedback is likely in the structural notes.",
    },
    {
        "id": 56,
        "temp_id": "B46",
        "source": "hand-designed",
        "name": "This looks good overall. Could we revisit the opening section?",
        "category": "Feedback framing",
        "implies": "Often, this signals satisfaction with most of the work and a specific request to revise the opening.",
        "why_misread": "You might hear the positive overall assessment as final approval. The question about the opening is still a meaningful revision request.",
    },
    {
        "id": 57,
        "temp_id": "B47",
        "source": "hand-designed",
        "name": "You've done a great job here. I wonder if the conclusion could be clearer.",
        "category": "Feedback framing",
        "implies": "There's genuine positive feedback, together with a likely request to make the conclusion easier to understand.",
        "why_misread": "It's easy to treat ‘I wonder’ as casual reflection. In feedback, it often introduces the main change the reader should consider.",
    },
    {
        "id": 58,
        "temp_id": "B48",
        "source": "hand-designed",
        "name": "I like where this is going. Maybe we should rethink the order.",
        "category": "Feedback framing",
        "implies": "This usually means the direction is working, but the sequence may need a substantive change.",
        "why_misread": "You might take ‘maybe’ as making the suggestion optional. It may be the sender's gentle way of identifying the central concern.",
    },
    {
        "id": 59,
        "temp_id": "B49",
        "source": "hand-designed",
        "name": "Almost there. There are just a couple of points to work through.",
        "category": "Feedback framing",
        "implies": "Often, this signals that the work is close to completion, but the remaining points still need resolution before approval.",
        "why_misread": "It's easy to hear ‘almost there’ as effectively finished. The second sentence indicates that completion still depends on further changes.",
    },
    {
        "id": 60,
        "temp_id": "B50",
        "source": "hand-designed",
        "name": "Thanks for pulling this together. One small concern is the level of detail.",
        "category": "Feedback framing",
        "implies": "There's appreciation for the work, alongside a concern that the amount of detail may need adjustment.",
        "why_misread": "You might treat a ‘small concern’ as optional. It may still affect whether the work is ready for its intended audience.",
    },
]


def public_record(card: dict) -> dict:
    return {field: card[field] for field in PUBLIC_FIELDS}


def normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def word_count(value: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", value))


def build() -> list[dict]:
    with DATASET_PATH.open(encoding="utf-8") as handle:
        original_cards = json.load(handle)

    if len(original_cards) == 60:
        original_cards = original_cards[:25]
    if len(original_cards) != 25 or [c["id"] for c in original_cards] != list(range(1, 26)):
        raise ValueError("Expected the reviewed 25-card baseline with IDs 1-25")

    expanded_records = original_cards + [public_record(card) for card in ADDITIONAL_CARDS]

    category_counts = Counter(card["category"] for card in expanded_records)
    ids = [card["id"] for card in expanded_records]
    names = [normalized_name(card["name"]) for card in expanded_records]
    empty_values = [
        (card["id"], field)
        for card in expanded_records
        for field in PUBLIC_FIELDS
        if card[field] is None or (isinstance(card[field], str) and not card[field].strip())
    ]
    style_violations = [
        (card["id"], field)
        for card in expanded_records
        for field in ("implies", "why_misread")
        if "—" in card[field] or "--" in card[field]
    ]
    new_word_count_violations = [
        (card["id"], field, word_count(card[field]))
        for card in expanded_records[25:]
        for field in ("implies", "why_misread")
        if word_count(card[field]) > 30
    ]

    assert len(expanded_records) == 60
    assert all(set(card) == set(PUBLIC_FIELDS) for card in expanded_records)
    assert not empty_values
    assert set(category_counts) == set(CATEGORIES)
    assert all(category_counts[category] == 10 for category in CATEGORIES)
    assert ids == list(range(1, 61))
    assert len(set(names)) == 60
    assert not style_violations
    assert not new_word_count_violations
    assert Counter(card["source"] for card in ADDITIONAL_CARDS) == {
        "real-corpus-derived": 5,
        "hand-designed": 30,
    }

    with DATASET_PATH.open("w", encoding="utf-8") as handle:
        json.dump(expanded_records, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    trace_by_id = {
        **{card_id: f"real-corpus-derived (A{card_id})" for card_id in range(1, 6)},
        **{card_id: f"hand-designed (B{card_id - 5})" for card_id in range(6, 26)},
    }
    for card in ADDITIONAL_CARDS:
        if card["source"] == "real-corpus-derived":
            trace_by_id[card["id"]] = (
                f"real-corpus-derived ({card['temp_id']}; Stanford Id {card['source_id']}; score {card['source_score']:.3f})"
            )
        else:
            trace_by_id[card["id"]] = f"hand-designed ({card['temp_id']})"

    lines = [
        "# Pattern Library — 60 Cards (Preview)",
        "",
        "For team review. Provenance labels are retained here for traceability and are not part of the exported JSON schema.",
        "",
        "| id | category | source | name | implies | why_misread |",
        "|---|---|---|---|---|---|",
    ]
    for card in expanded_records:
        values = [
            str(card["id"]),
            card["category"],
            trace_by_id[card["id"]],
            card["name"],
            card["implies"],
            card["why_misread"],
        ]
        escaped = [value.replace("|", r"\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    PREVIEW_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("wrote library_dataset.json with 60 records")
    print("wrote library_dataset_preview.md with 60 rows")
    print("category counts:", dict(category_counts))
    print("new-card provenance: 5 real-corpus-derived, 30 hand-designed")
    print("ALL EXPANSION CHECKS PASS")
    return expanded_records


if __name__ == "__main__":
    build()
