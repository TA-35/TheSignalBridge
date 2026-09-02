# API contract: frontendl-> Flask-> AI model

Draft. Update in the same PR that changes an endpoint's shape.

## `POST /api/decode`

Request:

```json
{ "message": "string, required, non-empty and non-meaningless" }
```

Response `200`:

```json
{
  "elements": {
    "time": "string | \"Not specified\"",
    "task": "string | \"Not specified\"",
    "deadline": "string | \"Not specified\"",
    "for_whom": "string | \"Not specified\""
  },
  "covered": ["time", "task"],
  "missing": [
    { "field": "deadline", "prompt": "What time is the client call due?" }
  ],
  "category": "one of the fixed category enum values — see below",
  "spans": {
    "time": [60, 63],
    "task": [0, 18],
    "deadline": null,
    "for_whom": null
  },
  "tasks": [
    {
      "text": "send the Q3 report",
      "span": [7, 25],
      "time": "Not specified",
      "deadline": "next Tuesday",
      "for_whom": "client",
      "missing": [{ "field": "time", "prompt": "What time do you need this by?" }]
    }
  ]
}
```

`spans` are `[start, end)` character offsets into the exact `message` string
sent, so the UI can highlight where each value came from. `null` when the
field is `"Not specified"`.

`tasks` is one entry per ask found in the message — a message with three
requests returns three. Each carries only the fields that fall inside its own
clause, so `missing` is scoped per bullet rather than per message. `elements`
remains the single-task view (the first ask) and is unchanged; clients can
migrate to `tasks` at their own pace. A message with no ask returns `[]`.

Response `400`: `{ "error": "Please enter a message" }` when empty or meaningless input.

**Rule:** the model must never fill in a value for an element the message doesn't state. Absent elements are `"Not specified"`.

## `GET /api/patterns`

Response `200`: array of pattern-library rows (curated content only, no user data):

```json
[
  {
    "id": "1",
    "name": "string",
    "category": "string",
    "implies": "what this phrasing usually implies",
    "why_misread": "why it tends to get misread"
  }
]
```

```json
example
[
  {
    "id": "1",
    "name": "Before the sync",
    "category": "Vague deadline",
    "implies": "A deadline anchored to an event, not a time. The sender assumes you know when that event is.",
    "why_misread": "Event anchors feel precise to the sender and unknowable to the reader, so the gap goes unnoticed by both."
  }
]
```

Rows have no citation field. AC 2.2.2's "source label per card" requirement
was dropped by the content team — flag this if AC 2.2.2 is still being
graded against, since the schema no longer satisfies it.

## Category enum

The AI model's classification output must be bounded to a fixed set of category strings that match `patterns.category` rows cuz free text `breaks` the pattern-library join silently.

**Values**, from the real content in `data/library_dataset/library_dataset.json` (25 rows, content team's authoring pass — see build plan §7):

- `Softened request`
- `Vague deadline`
- `Unassigned owner`
- `Feedback framing`
- `Unclear priority`
- `Undefined scope`

Implemented in `backend/app/services/ai_decoder.py` (`_CATEGORY_RULES`) and mirrored in `frontend/src/services/localPatterns.ts` (`CATEGORY_TRIGGERS`) for the offline fallback — keep both in step if this list changes again.

## Data retention

No message text, extracted elements, or saved cards are ever persisted server-side or logged.

On the client, decodes and saved cards are written to `localStorage` on the
user's own device, so a decode survives a refresh and a card can point back at
the message that produced it. The decode history is capped at 100 records.
This is the only place message text is written to disk; nothing is uploaded,
and Settings -> "clear" removes all of it.
