# Google Calendar Integration

Lets a staff member (an `Associate`) connect their Google Calendar, so their
appointments in this system can show up there too - with a Google Meet link
attached automatically.

**Status: not live yet.** The code is written and the database tables are
defined, but nothing is turned on.

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
4. **We save those tokens**, encrypted, in a `GoogleCalendarConnection` row -
   one per associate.
5. **When an appointment is created/rescheduled/cancelled**, we call
   `insert_event()` / `patch_event()` / `delete_event()` to create or update
   the matching event on that staff member's Google Calendar and save the
   Google event's ID + Meet link in a `GoogleCalendarEvent` row.
6. **Before every Google API call**, `get_valid_access_token()` checks if the
   saved access token has expired - if so, it silently uses the refresh token
   to get a new one first.

## The files

All under `integrations/google_calendar/`:

| File              | What it does                                                                                                                                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.py`       | Reads the Google API credentials (client ID/secret, redirect URL, encryption key) from Django settings, per environment — see `ORANGE_LABS_*` in `core/settings/{development,staging,production}.py` for the same pattern. |
| `utils.py`        | Small helpers: current time in IST and encrypt/decrypt for tokens before they touch the database.                                                                                                                          |
| `google_oauth.py` | Talks to Google's _login_ side - builds the consent screen URL, trades codes for tokens, refreshes tokens, looks up the connected email, revokes access.                                                                   |
| `calendar_api.py` | Talks to Google's _calendar_ side - create/update/list/delete events on someone's calendar.                                                                                                                                |
| `tokens.py`       | The glue: given a saved connection, hands back a token that's guaranteed to still be valid (refreshing it first if needed).                                                                                                |

The two database tables (`GoogleCalendarConnection`, `GoogleCalendarEvent`)
live in `integrations/models.py`, alongside every other model this app owns.

## The two database tables

Both defined in `integrations/models.py`. Both also inherit `BaseUUIDModel`
(`core/utils/models.py`), which is where the first four columns of every
table below come from - every model in this project gets these for free.

### `GoogleCalendarConnection`

One row per staff member who connected their Google account.

| Column                     | Data type                                         | Purpose                                                                                                 |
| -------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `id`                       | UUID (primary key)                                | Unique ID for this row. From `BaseUUIDModel`.                                                           |
| `is_active`                | Boolean                                           | Whether this row is still considered valid. From `BaseUUIDModel`.                                       |
| `created_at`               | DateTime                                          | When this row was first saved. From `BaseUUIDModel`.                                                    |
| `updated_at`               | DateTime                                          | When this row was last changed. From `BaseUUIDModel`.                                                   |
| `associate`                | Foreign key → `associates.Associate` (one-to-one) | Which staff member this connection belongs to. Real column name in Postgres is `associate_id`.          |
| `google_email`             | Email (unique)                                    | The Google account's email address, shown in the UI as "Connected as \_\_\_".                           |
| `access_token`             | Text                                              | The short-lived Google API token, encrypted before it's saved (see `utils.encrypt`).                    |
| `refresh_token`            | Text                                              | The long-lived token used to get a new access token once it expires, encrypted the same way.            |
| `access_token_expires_at`  | DateTime (nullable)                               | When `access_token` stops being valid - checked by `tokens.is_expired()`.                               |
| `sync_token`               | Text, up to 255 characters (blank allowed)        | Reserved for incremental calendar sync (fetching only what changed since last check). Not used yet.     |
| `watch_channel_id`         | Text, up to 255 characters (blank allowed)        | Reserved for Google's push-notification feature (Google pings us when something changes). Not used yet. |
| `watch_channel_expiration` | DateTime (nullable)                               | When that push-notification subscription expires. Not used yet.                                         |

### `GoogleCalendarEvent`

One row per appointment that's been mirrored onto Google Calendar. Deliberately
does **not** repeat fields that already exist on `Appointment` (title,
start/end time, notes, location) - it only stores what Google adds on top.

| Column               | Data type                                                  | Purpose                                                                                                          |
| -------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `id`                 | UUID (primary key)                                         | Unique ID for this row. From `BaseUUIDModel`.                                                                    |
| `is_active`          | Boolean                                                    | Whether this row is still considered valid. From `BaseUUIDModel`.                                                |
| `created_at`         | DateTime                                                   | When this row was first saved. From `BaseUUIDModel`.                                                             |
| `updated_at`         | DateTime                                                   | When this row was last changed. From `BaseUUIDModel`.                                                            |
| `appointment`        | Foreign key → `appointments.Appointment` (one-to-one)      | Which real appointment this event mirrors. Real column name in Postgres is `appointment_id`.                     |
| `google_event_id`    | Text, up to 255 characters, indexed                        | The ID Google assigned this event - needed to update (`patch_event`) or cancel (`delete_event`) it later.        |
| `meet_link`          | URL (blank allowed)                                        | The Google Meet video link Google generated for this event, if one was requested.                                |
| `participant_emails` | List of emails (Postgres array, defaults to an empty list) | Everyone invited to this event on the Google side - may not exactly match `appointment.customer`'s contact info. |

## Required `.env` values

Following the same per-environment pattern as `ORANGE_LABS_*` in
`core/settings/{development,staging,production}.py` — each environment reads
its own prefixed variable (`DEV_`/`STG_`/`PRD_`) into a plain settings
constant and `integrations/google_calendar/config.py` reads those constants
via `django.conf.settings` (not `.env` directly). Locally, add these to `.env`:

```
DEV_GOOGLE_CLIENT_ID=
DEV_GOOGLE_CLIENT_SECRET=
DEV_GOOGLE_REDIRECT_URI=
DEV_GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY=
DEV_ADMIN_FRONTEND_URL=
```

`DEV_GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` isn't a password you make up -
generate it with:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Staging and production use the same variable names with `STG_`/`PRD_`
prefixes instead, set wherever that environment's secrets live.

## A note on tokens and security

Access and refresh tokens are never stored as plain text - `utils.encrypt()`
scrambles them before saving, `utils.decrypt()` unscrambles them right before
they're sent to Google. If the encryption key
(`GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY`) ever leaks, treat it like a leaked
password - rotate it and have every connected staff member reconnect.
