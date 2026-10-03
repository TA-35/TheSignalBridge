# API contract: frontendl-> Flask-> AI model

Draft. Update in the same PR that changes an endpoint's shape.

## `POST /api/decode`

Request:

```json
{ "message": "string, required, non-empty and non-meaningless, max 5000 characters" }
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

Response `413`: `{ "error": "Message is too long (limit is 5000 characters)." }` when
`message` exceeds the limit above. The same shape (`{ "error": "Request is
too large." }`) is also returned if the raw request body itself exceeds
`MAX_CONTENT_LENGTH` (100 KB), which is rejected before the body is even
parsed. Mirrored client-side by `MAX_MESSAGE_LENGTH` in
`frontend/src/services/decodeService.ts` - keep both in step if this changes.

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

## Accounts: `/api/account/*`

Optional, and additive - every endpoint above behaves identically signed in
or out. Authentication is a passkey (WebAuthn); there is no password and no
email. How the flows fit together, and why, is in [accounts.md](accounts.md).

Every call carries the session cookie, so the frontend sends
`credentials: 'include'` and the API answers with
`Access-Control-Allow-Credentials`.

| endpoint | body | success | notes |
| --- | --- | --- | --- |
| `POST /register/options` | – | `200` WebAuthn creation options | mints a handle; writes no row yet |
| `POST /register/verify` | the browser's attestation | `201 {handle, created_at}` | creates the account, signs in |
| `POST /login/options` | – | `200` WebAuthn request options | no `allowCredentials` - passkeys are discoverable |
| `POST /login/verify` | the browser's assertion | `200 {handle, created_at}` | signs in |
| `POST /pairing` | – | `201 {code, handle, expires_at, expires_in_minutes}` | signed in only; retires any earlier code |
| `POST /pairing/claim` | `{handle, code}` | `200` WebAuthn creation options | single use, ten-minute life |
| `POST /pairing/verify` | the browser's attestation | `201 {handle, created_at}` | adds a passkey to the existing account, signs in |
| `GET /me` | – | `200 {handle, created_at}` / `401` | 401 is the signed-out answer, not an error |
| `POST /logout` | – | `200 {ok: true}` | |
| `DELETE /api/account` | – | `200 {ok: true}` / `401` | removes the user, its passkeys and its codes |

The account object is the whole of it:

```json
{ "handle": "7KQ2", "created_at": "2026-10-04T02:11:30+00:00" }
```

**Rule:** the handle is an identifier, never a credential. Four characters is
about a million combinations, so no endpoint grants anything for knowing one
- `/pairing/claim` takes a handle only to narrow which code it is checking.

**Error shapes.** `400` for a failed or expired flow, `401` for "not signed
in", `409` if a handle could not be allocated, `429` from the rate limiter.
Verification failures all answer `{"error": "That passkey could not be
verified."}` and pairing failures all answer `{"error": "That code is not
valid. Ask for a new one."}` - wrong, expired, and unknown are deliberately
indistinguishable, so neither endpoint can be used to discover which accounts
exist.

## Data retention

No message text, extracted elements, or saved cards are ever persisted server-side or logged.

On the client, decodes and saved cards are written to `localStorage` on the
user's own device, so a decode survives a refresh and a card can point back at
the message that produced it. The decode history is capped at 100 records.
This is the only place message text is written to disk; nothing is uploaded,
and Settings -> "clear" removes all of it.

Accounts do not change that. A signed-in account holds a four-character
handle, two timestamps, and the public half of each registered passkey -
no message text, no saved cards, no email, no password hash. Saved cards
stay in the browser whether or not anyone is signed in, which is also why
deleting an account leaves them untouched.
