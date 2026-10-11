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

## `POST /api/compose`

**Built, not yet deployed.** The backend route is `backend/app/routes/compose.py`;
the work happens on the inference service (`Src/source/pipeline/compose_service.py`),
which needs `requirements-compose.txt` and a llama-server running the rewrite model.

The other direction from `/api/decode`. The sender pastes a message they
have already written; the response says the same thing more explicitly,
with a short account of what changed.

The response shape is the training record from the data team's build guide
(`meaning`, `rewrite`, `notes`), so the model's own output drops straight in
without a translation layer. Keep these names.

Request:

```json
{ "message": "string, required, non-empty, max 2000 characters" }
```

2000, not Decode's 5000: the model was trained on messages up to ~1,500
characters, and much past 2,000 its reply outgrows its token budget.

Response `200`:

```json
{
  "stage": "compose",
  "degraded": false,
  "degraded_reason": [],
  "rewrite": "Please send me the Q3 numbers before Friday's 2pm sync.",
  "notes": [
    "'Might be good' was a polite way of asking - this is required",
    "The deadline was implied, so it's now stated"
  ],
  "meaning": {
    "ask": "Send the Q3 numbers",
    "deadline": "Before Friday's sync",
    "urgency": "high",
    "tone": "friendly",
    "implied": "Required, not optional"
  },
  "signals": [{ "model": "politeness", "label": "high", "confidence": 0.65 }],
  "checks": { "entities_kept": true, "nothing_added": true, "no_contradiction": true },
  "model": "qwen3.5-4b-ft"
}
```

`degraded_reason` values:

| value | meaning |
| --- | --- |
| `dropped_entity`, `added_entity`, `contradiction` | the grounding check rejected the rewrite, twice (it retries once at a lower temperature) |
| `invalid_output` | the model's reply wasn't usable, twice |
| `model_unavailable` | llama-server couldn't be reached or errored; not retried |
| `not_configured` | `COMPOSE_LLM_URL` isn't set on the inference host |
| `check_unavailable` | the grounding check couldn't run, so nothing could be verified |
| `inference service ...`, `compose error: ...` | the proxy or the service failed; names the error class only |

The page words the first row as "didn't pass our fact check" and everything
else as "couldn't be reached" (`failedFactCheck` in `frontend/src/types/compose.ts`).

`POST /api/compose/quick` runs the three classifiers only and returns
`{ "stage": "analyse", "signals": [...] }` in milliseconds, so the page can
paint before the rewrite lands.

**No tone parameter, on purpose.** The rewrite keeps the register of the
draft: the classifier signals tell the model what that register is, and the
eval harness penalises a rewrite whose politeness band drops. `meaning.tone`
is an observation about the message, never an instruction. A tone or
formality selector would promise something the model is not trained to do -
see [the data team's build guide](../TheSignalBridge%20—%20Data%20Team%20How-To%20Guide%20(Final%20Build).pdf).

**Three states the frontend renders, so all three must be answerable:**

1. **Rewritten.** `rewrite` is a string, `notes` has 2-3 entries.
2. **Already clear.** `notes` is exactly `["Already clear, kept as written."]`
   and the rewrite is near-identical to the source. The page says so rather
   than presenting an unchanged message as a result.
3. **No rewrite.** `rewrite` is `null` and `degraded` is `true` - the
   grounding check found a dropped or invented fact, or the model could not
   be reached. `degraded_reason` names the class of failure, never the
   message body.

**A rewrite that fails the grounding check must not be returned at all.**
It reads as finished text and would be pasted into an email. Send `null` and
let the page explain itself; the client drops any rewrite that arrives with
`degraded: true` as a backstop.

Response `400` / `413`: same shapes as `/api/decode`.

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

## Library cards: `/api/cards`

Signed-in only; `401` otherwise. These are the cards an account carries
between devices, stored as a pointer rather than as content: which curated
pattern, when it was kept, when it was last opened.

| endpoint | body | success |
| --- | --- | --- |
| `GET /api/cards` | – | `200 [{pattern_id, saved_at, last_opened_at}]` |
| `PUT /api/cards/<pattern_id>` | `{saved_at?, last_opened_at?}` | `200` the stored row |
| `DELETE /api/cards/<pattern_id>` | – | `200 {ok: true}` |

`PUT` is an upsert and is meant to be replayed: a device signing in sends
everything it has. Conflicts resolve by time - the **earliest** `saved_at`
wins (that is when the reader actually kept it) and the **latest**
`last_opened_at` wins. `DELETE` answers `200` whether or not a row was
there; removing a card the server never had is the two sides agreeing.

**Only library cards sync.** A card made from a decode carries an excerpt of
the reader's own message, so it stays in the browser that made it. A second
device therefore shows the library cards and not those - a deliberate limit,
not a gap. The browser remains the source of truth either way: the Study
page reads `localStorage`, and a failed sync never costs a saved card.

## Progress: `/api/progress`

Signed-in only; `401` otherwise. The progress dashboard's data, so days and
badges follow an account between devices. Same rules as `/api/cards`: the
browser stays the source of truth, `PUT` is an idempotent upsert meant to be
replayed, and nothing the reader typed travels. The focus timer's
"what are you working on?" text stays in the browser and has no column.

| endpoint | body | success |
| --- | --- | --- |
| `GET /api/progress` | – | `200 {activity, phrase_events}` |
| `PUT /api/progress` | `{device_id, activity, phrase_events}` | `200 {activity, phrase_events, skipped}` - the account's whole set after merging |
| `DELETE /api/progress` | – | `200 {ok: true}` |

```json
{
  "device_id": "random id the browser made for itself",
  "activity": [
    { "date": "2026-10-09", "feature": "opened", "minutes": 0 },
    { "date": "2026-10-09", "feature": "decoder", "minutes": 12 }
  ],
  "phrase_events": [
    { "pattern_id": "7", "kind": "reviewed", "date": "2026-10-09" }
  ]
}
```

- `feature` is one of `opened`, `decoder`, `compose`, `study`, `library`.
  `opened` with 0 minutes is a day the app was used at all, which is what the
  badges count. `kind` is `viewed` or `reviewed`. Dates are the reader's own
  calendar day.
- Minutes are stored per device, and the **highest** number wins for a
  device's day and feature, because a browser's total only goes up. Keeping
  devices apart is what lets the dashboard add a laptop and a phone together
  without double counting either one's replay. GET returns `device_id` on each
  activity row for that reason; it is a random string, not a fingerprint.
- Phrase events are a set: sending one twice is one row.
- Rows that don't parse are skipped, not fatal, and counted in `skipped`. A
  missing or malformed `device_id` is `400`; more than 2000 activity rows or
  5000 phrase events in one request is `413`.
- `DELETE` is Settings' "delete" while signed in, so cleared progress doesn't
  sync back down. Deleting the account removes these rows too.

## Data retention

No message text, extracted elements, or saved cards are ever persisted server-side or logged.

On the client, decodes and saved cards are written to `localStorage` on the
user's own device, so a decode survives a refresh and a card can point back at
the message that produced it. The decode history is capped at 100 records.
This is the only place message text is written to disk; nothing is uploaded,
and Settings -> "clear" removes all of it.

Accounts do not change that. A signed-in account holds a four-character
handle, two timestamps, and the public half of each registered passkey, plus
the library cards and progress described above: pattern ids, dates, feature
names and minute counts. No message text, no email, no password hash, and
never anything the reader typed, including the focus timer's intent text.
The browser's own copy of cards and progress stays put whether or not anyone
is signed in, which is also why deleting an account leaves this device's copy
untouched. Settings -> "delete" clears both, and the account's copy too when
signed in.
