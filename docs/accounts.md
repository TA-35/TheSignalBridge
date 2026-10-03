# Accounts and passkeys

How signing in works, end to end. Endpoint shapes live in
[api-contract.md](api-contract.md); this is the part that explains why the
pieces are arranged the way they are.

Everything here is additive. `/api/decode`, `/api/patterns` and `/api/review`
behave exactly as before, signed in or out, and every page works without an
account. An account changes what the app can *remember*, never what it can
*do*.

## Why passkeys and not a password

The project is not allowed to hold passwords. A passkey is not one:

- The browser generates a key pair. The **private** key stays in the reader's
  device or password manager and never reaches us.
- We store the **public** half. A database dump contains nothing that can be
  replayed anywhere.
- Signing in means the device signs a one-time challenge; the server checks
  the signature against the stored public key.

The library doing the checking is [py_webauthn](https://pypi.org/project/webauthn/)
(`webauthn==3.0.1`), pinned in `backend/requirements.txt`.

## The four-character ID

`7KQ2`, `B4NX`. Crockford's alphabet, minus `I`, `L`, `O` and `U` - the three
that get misread off a screen, plus one that keeps accidental words out.

**It is an address, not a credential.** Four characters is about a million
combinations, which anyone can walk through in an afternoon, so nothing is
ever granted by knowing one. It exists so a person can recognise their own
account, read it out to a teammate, and pair a second device. Internally
every row keys on a UUID, never on the handle.

Uniqueness is the unique index on `users.handle`. The route re-rolls the
handle and retries up to eight times if it collides.

## Database

Three tables, in two migrations: `b2c7a1d4e905` (users, credentials) and
`c93e60f12a47` (pairing codes).

### `users`

| column | type | notes |
| --- | --- | --- |
| `id` | `varchar(36)` PK | UUID. Everything foreign-keys to this |
| `handle` | `varchar(8)` unique | the four characters shown to the reader |
| `created_at` | timestamptz | |
| `last_seen_at` | timestamptz | written on every sign-in |

No email, no name, no password hash.

### `credentials`

One row per registered passkey. A reader can have several - laptop, phone,
hardware key.

| column | type | notes |
| --- | --- | --- |
| `id` | `serial` PK | |
| `user_id` | FK → `users.id` | `ON DELETE CASCADE` |
| `credential_id` | `bytea` unique | the authenticator's id for this key |
| `public_key` | `bytea` | the public half |
| `sign_count` | `int` | authenticator's counter, see below |
| `transports` | `varchar(120)` | nullable |
| `created_at` / `last_used_at` | timestamptz | |

`sign_count` has to be stored and updated on every sign-in: authenticators
increment it, and a counter that goes *backwards* is how a cloned key is
detected. The library performs that check, but only if we hand it the last
value we saw.

### `pairing_codes`

| column | type | notes |
| --- | --- | --- |
| `id` | `serial` PK | |
| `user_id` | FK → `users.id` | `ON DELETE CASCADE` |
| `code_hash` | `varchar(64)` unique | SHA-256. The plaintext is never stored |
| `created_at` / `expires_at` | timestamptz | ten-minute life |
| `consumed_at` | timestamptz | set on redemption; a code works once |

**Note on cascades.** The foreign keys say `ON DELETE CASCADE`, but the ORM
relationships deliberately do *not* set `passive_deletes`. SQLAlchemy deletes
the children itself, and the database constraint is the backstop for a
`DELETE` run by hand. SQLite does not enforce foreign keys by default, and
the test suite caught exactly this - "delete my account" was leaving
credentials behind.

## The three flows

### Creating an account

```
browser                          API
   |  POST /api/account/register/options
   |------------------------------------>|  mint a UUID + handle (NOT saved yet)
   |                                     |  generate_registration_options()
   |<------------------------------------|  challenge, stored in the session cookie
   |
   |  navigator.credentials.create()      (fingerprint / Face ID / PIN)
   |
   |  POST /api/account/register/verify
   |------------------------------------>|  verify_registration_response()
   |                                     |  INSERT users + credentials
   |<------------------------------------|  201 {handle}, session cookie set
```

No row is written until verification succeeds, so a reader who opens the
system prompt and changes their mind leaves nothing behind - no empty account
holding a handle nobody uses.

### Signing in

```
   |  POST /api/account/login/options   -> challenge
   |  navigator.credentials.get()        (browser offers the accounts it holds)
   |  POST /api/account/login/verify    -> 200 {handle}, session cookie set
```

The credentials are **discoverable** (`resident_key=REQUIRED`), which is why
nobody types an ID to sign in: the browser already knows which accounts exist
for this site and offers them. The server identifies the account from the
credential id in the signed response.

`allow_credentials` is deliberately empty. Sending the list would mean
accepting an identifier *before* anything is proved, which turns the endpoint
into a way to test which accounts exist.

### Pairing a second device

A passkey cannot be copied. An account made in Chrome is stranded there
unless that password manager syncs it - so the second device registers its
**own** passkey, authorised by a code from a device that is already signed in.

```
laptop (signed in)                       API
   |  POST /api/account/pairing        -> {code: "4F7K2Q", expires_in_minutes: 10}
                                          (any earlier live code is retired)

phone (knows nothing)
   |  POST /api/account/pairing/claim  <- {handle, code}
   |                                     match on SHA-256, check expiry + handle
   |                                     mark consumed, return registration options
   |  navigator.credentials.create()
   |  POST /api/account/pairing/verify -> 201 {handle}, INSERT credentials, signed in
```

Four decisions worth knowing:

- **The code buys a registration, not a session.** Between `claim` and
  `verify`, `/api/account/me` still answers 401. Whoever uses a code has to
  leave a passkey behind, which is traceable, rather than slipping into a
  session.
- **Spent on claim, not on success.** An abandoned prompt burns the code. The
  alternative leaves a live code sitting in a closed tab.
- **`exclude_credentials` carries the account's existing keys**, so the
  authenticator refuses to make a second one for a device that is already
  paired.
- **Every failure returns the same sentence** - wrong code, expired code,
  wrong handle, unknown account. Distinguishing them would turn the endpoint
  into an oracle for which handles exist.

## Sessions

An HttpOnly cookie, not a token in `localStorage`: script on the page cannot
read it, which matters because the page renders text the user pasted in.

- `SESSION_COOKIE_NAME=bw_session`, `HttpOnly`, `SameSite=Lax`
- `SESSION_COOKIE_SECURE` defaults to **true**; local dev runs on plain http,
  where a Secure cookie is dropped, so `backend/.env` sets it false
- In production the site (`thesignalbridge.com`) and the API
  (`api.thesignalbridge.com`) are different hosts under one registrable
  domain, so `SESSION_COOKIE_DOMAIN=.thesignalbridge.com` - same-site, which
  is why `Lax` is enough
- CORS runs with `supports_credentials=True`, and every frontend call sends
  `credentials: 'include'`. Both halves are required; with one missing the
  cookie is set and never sent back, which looks exactly like "signing in
  does nothing"

The WebAuthn challenge also lives in the session between the two calls of
each flow. It is single-use, short-lived, and useless without the private
key, so a signed cookie is the right place for it - and an abandoned flow
leaves no row to clean up.

## Configuration

| variable | local | production |
| --- | --- | --- |
| `WEBAUTHN_RP_ID` | `localhost` | `thesignalbridge.com` |
| `WEBAUTHN_RP_NAME` | `BetweenWords` | same |
| `WEBAUTHN_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | `https://thesignalbridge.com,https://www.thesignalbridge.com` |
| `SESSION_COOKIE_SECURE` | `false` | unset (defaults true) |
| `SESSION_COOKIE_DOMAIN` | unset | `.thesignalbridge.com` |

The RP ID must be the registrable domain the page is served from, so one
passkey works on the site and against the API. A wrong value fails every
registration with a vague browser error and no server log - check this first
when passkeys stop working after a deploy.

## Running it locally

```sh
cd backend
cp .env.example .env          # fill in SECRET_KEY, DATABASE_URL
flask db upgrade              # creates users, credentials, pairing_codes
flask run
```

Then open `http://localhost:5173/account`. `localhost` is a secure context as
far as WebAuthn is concerned, so no certificate is needed.

```sh
cd backend && pytest tests/test_account_route.py   # 21 tests
```

The tests stub the signature check and exercise everything around it -
sessions, handles, pairing, failure shapes, deletion. Reproducing a real
authenticator would test py_webauthn rather than our code.

## Frontend

| file | role |
| --- | --- |
| `src/services/accountService.ts` | the browser's WebAuthn calls, base64url ↔ ArrayBuffer, `credentials: 'include'` |
| `src/stores/account.ts` | who is signed in; `ready` guards the first paint |
| `src/views/AccountView.vue` | `/account` - sign in, create, pairing, deletion |
| `src/layouts/AppShell.vue` | header: "Login" when signed out, the ID and a menu when signed in |

`/login` redirects to `/account`. The store is refreshed once per page load
from `AppShell`, so the header never says "Login" to someone already signed
in.

## Known limits

- **A passkey belongs to the password manager that made it.** One created in
  Chrome (Google Password Manager) will not appear in Edge (Windows Hello).
  The ways across are the phone-over-QR option in the browser's own dialog,
  or a pairing code. This is platform behaviour, not something the code can
  fix.
- **Lose every device and the account is gone.** There is no recovery by
  design - a recovery secret would be the password we are not allowed to
  hold. The mitigation is to register a second passkey early, which is what
  pairing is for.
- **A pairing code is something the reader types.** It is single-use, expires
  in ten minutes, is never chosen by the user and is stored only as a hash,
  so it is not a password in any meaningful sense - but if the unit's rules
  are read strictly, flag it before the demo rather than after.
- **Rate limits are per worker.** Three gunicorn workers mean roughly 3× the
  configured limit in the worst case; see `app/limiter.py` for why that is
  acceptable here.
