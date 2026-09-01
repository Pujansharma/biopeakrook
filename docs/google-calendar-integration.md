# Google Calendar Integration

Lets a staff member (an `Associate`) connect their Google Calendar, so their
appointments in this system can show up there too - with a Google Meet link
attached automatically.

**Status: not live yet.** The connect/callback/disconnect endpoints and
Google API client are written, but the database columns they need don't
exist yet - see `integrations/google_calendar/db.md` for exactly what's
pending.

---

## Why this exists

Today, an `Appointment` in this system only exists in our own database. Staff
don't get it on their phone/laptop calendar unless someone tells them by hand.
This integration mirrors an appointment onto the staff member's own Google
Calendar, so they get the normal Google reminders and a video call link if
the appointment needs one.

## How it works, end to end

1. **Staff member clicks "Connect Google Calendar"** somewhere in the admin
   frontend. That takes them to a URL built by `build_auth_url()` - Google's
   own consent screen, asking "allow this app to manage your calendar events?"
2. **Staff member approves it.** Google redirects their browser back to us
   with a one-time code.
3. **We trade that code for tokens** using `exchange_code()` - Google gives us
   back an `access_token` (short-lived, ~1 hour) and a `refresh_token`
   (long-lived, doesn't expire until revoked).
4. **We save those tokens**, encrypted, directly on that staff member's
   `Associate` row (see `db.md` for the column list).
5. **When an appointment is created/rescheduled/cancelled**, we call
   `insert_event()` / `patch_event()` / `delete_event()` to create or update
   the matching event on that staff member's Google Calendar and save the
   Google event's ID + Meet link on the `Appointment` row (not wired into
   appointment creation yet).
6. **Before every Google API call**, `get_valid_access_token()` checks if the
   saved access token has expired - if so, it silently uses the refresh token
   to get a new one first.

## The files

All under `integrations/google_calendar/`:

| File              | What it does                                                                                                                                                                                                                                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `utils.py`        | Encrypt/decrypt for tokens before they touch the database. Reads the encryption key from Django settings and builds the Fernet cipher lazily on first use, so importing this module doesn't require the key to be configured.                                                                                      |
| `google_oauth.py` | Talks to Google's _login_ side - builds the consent screen URL, trades codes for tokens, refreshes tokens, looks up the connected email, revokes access. Reads its own client ID/secret/redirect URL from Django settings, same pattern as `ORANGE_LABS_*` in `core/settings/{development,staging,production}.py`. |
| `calendar_api.py` | Talks to Google's _calendar_ side - create/update/list/delete events on someone's calendar.                                                                                                                                                                                                                        |
| `tokens.py`       | The glue: given an associate, hands back a token that's guaranteed to still be valid (refreshing it first if needed).                                                                                                                                                                                              |
| `db.py`           | Persists a refreshed access/refresh token onto the `Associate` row via `save(update_fields=...)` - only the columns that changed, not a full-row save.                                                                                                                                                             |
| `state.py`        | Builds/verifies the OAuth `state` value - a signed token (Django's `django.core.signing`, no server-side storage needed) that ties the callback back to the associate who started the connect flow. See "Connect/disconnect endpoints" below.                                                                      |
| `views.py`        | The three HTTP endpoints associates actually hit: connect, callback, disconnect. See below.                                                                                                                                                                                                                        |
| `urls.py`         | Routes those three views under `/google-calendar/`.                                                                                                                                                                                                                                                                |
| `db.md`           | The exact `Associate`/`Appointment` columns this feature needs and why - not yet migrated. See there for the full column list.                                                                                                                                                                                     |

`integrations/models.py` is empty - this feature doesn't get its own tables.
Connection/event data lives directly on `Associate` and `Appointment`
(pending migration, see `db.md`).

## Connect/disconnect endpoints

| Endpoint                              | Auth            | What it does                                                                                                                                                       |
| ------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /google-calendar/connect/`       | Associate (JWT) | Returns Google's consent-screen URL as JSON (`{"data": {"auth_url": "..."}}`). The frontend navigates the browser there itself.                                    |
| `GET /google-calendar/callback/`      | None (public)   | Google redirects the browser here after consent. Always ends in a redirect back to `ADMIN_FRONTEND_URL` with `?connected=1&email=...` or `?connected=0&error=...`. |
| `DELETE /google-calendar/disconnect/` | Associate (JWT) | Revokes the token with Google and clears the signed-in associate's own `google_*` columns.                                                                         |

**Why `/connect/` doesn't redirect directly:** the callback (`/callback/`) is a
plain browser navigation triggered by Google - it can't carry our
`Authorization` header. So `/connect/` is a normal authenticated JSON
endpoint the frontend calls first; the frontend itself then sends the
browser to the returned `auth_url`.

**Why `/callback/` is unauthenticated but still safe:** the associate it
acts on is never taken from a query param or client input - it's decoded
from the signed `state` value that `/connect/` minted for that specific
associate (`state.py`), which can't be forged without the app's
`SECRET_KEY` and expires after 10 minutes. A request with a missing,
tampered, expired, or reused `state` is rejected before anything is
written to the database.

**Why `/disconnect/` takes no id in the URL:** it always acts on
`request.user.associate`, the associate the JWT belongs to - never a
client-supplied associate/staff id - so one associate can never disconnect
another's calendar.

## Database columns

No dedicated tables - the columns this feature needs go directly on
`Associate` (connection: email, tokens, expiry) and `Appointment` (mirrored
event: Google event id, Meet link). Full column list, types and reasoning:
`integrations/google_calendar/db.md`. **Not migrated yet** - the code in this
package reads/writes these columns, but they don't exist on the real tables
until that migration lands.

## Rescheduling and Meet links

`patch_event()` takes `add_meet_link`, not `need_meet_link` - and it must only
be passed `True` the first time a Meet link is being added to an event.
Passing it `True` on an event that already has one sends Google a fresh
`conferenceData.createRequest`, which creates a brand new conference and
rotates the Meet link, stranding anyone holding the old one. Ordinary
reschedules should leave it `False`.

`patch_event()` also always sends `location` / `description` / `attendees` in
the body (empty when unset), unlike `insert_event()` which omits them when
not given - Google's PATCH only touches the keys present in the request, so
omitting a field there would leave the previous value in place instead of
clearing it.

## Required `.env` values

Same per-environment pattern as `ORANGE_LABS_*` in
`core/settings/{development,staging,production}.py` - each environment reads
its own prefixed variable (`DEV_`/`STG_`/`PRD_`) into a plain settings
constant, which `google_oauth.py` (and `utils.py` for the encryption key)
reads via `django.conf.settings`. See `docs/ENVIRONMENT.md` for the full list
alongside every other integration's env vars.

`GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` isn't a password you make up -
generate it with:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## A note on tokens and security

Access and refresh tokens are never stored as plain text - `utils.encrypt()`
scrambles them before saving, `utils.decrypt()` unscrambles them right before
they're sent to Google. If the encryption key
(`GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY`) ever leaks, treat it like a leaked
password - rotate it and have every connected staff member reconnect.
