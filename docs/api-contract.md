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
  "category": "one of the fixed category enum values — see below"
}
```

Response `400`: `{ "error": "Please enter a message" }` when empty or meaningless input.

**Rule:** the model must never fill in a value for an element the message doesn't state. Absent elements are `"Not specified"`.

## `GET /api/patterns`

Response `200`: array of pattern-library rows (curated content only, no user data):

```json
[
  {
    "id": 1,
    "name": "string",
    "category": "string",
    "implies": "what this phrasing usually implies",
    "why_misread": "why it tends to get misread",
    "source": "citation for the explanation"
  }
]
```

```json
example
[
  {
    "id": 1,
    "name": "Before the sync",
    "category": "Vague deadline",
    "implies": "A deadline anchored to an event, not a time. The sender assumes you know when that event is.",
    "why_misread": "Event anchors feel precise to the sender and unknowable to the reader, so the gap goes unnoticed by both.",
    "source": "Clark, Using Language (1996) — common-ground assumptions in reference"
  }
]
```

## Category enum

The AI model's classification output must be bounded to a fixed set of category strings that match `patterns.category` rows cuz free text `breaks` the pattern-library join silently.

**Draft values** (from the frontend's local seed content — `frontend/src/services/localPatterns.ts` — pending the real content-authoring pass in build plan §7):

- `Softened request`
- `Vague deadline`
- `Unassigned owner`
- `Feedback framing`

Confirm/extend this list once the pattern library (15–25 rows) is written, then update this doc and the seed data together.

## Data retention

No message text, extracted elements, or saved cards are ever persisted server-side or logged.
