# Google Calendar — database columns to add

Google Calendar sync does **not** get its own new tables. Instead, a handful
of columns get added to two tables that already exist:

- `Associate` (`accounts/associates/models.py`) — one row already exists per
  staff member
- `Appointment` (`appointments/models.py`) — one row already exists per
  booked appointment

This page lists exactly which columns, on which table and why each one is
needed.

---

## Table 1: `Associate`

**File:** `accounts/associates/models.py`

Each staff member can connect their own Google account once. The connection
info is stored directly on their existing row.

| New column                       | Type                   | What it stores                                                         | Why we need it                                                                                                                                         |
| -------------------------------- | ---------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `google_email`                   | Email (optional)       | The Google account's email, e.g. `priya@gmail.com`                     | Shown in the UI as "Connected as \_\_\_" and confirms which Google account is linked.                                                                  |
| `google_access_token`            | Text (optional)        | An encrypted, short-lived Google access key (expires in about an hour) | Needed to make Google Calendar API calls on the staff member's behalf. Encrypted before saving — never stored as plain text.                           |
| `google_refresh_token`           | Text (optional)        | An encrypted, long-lived Google key that doesn't expire on its own     | Used to get a new `google_access_token` automatically once the old one expires, without asking the staff member to reconnect. Encrypted before saving. |
| `google_access_token_expires_at` | Date + time (optional) | When `google_access_token` stops working                               | Lets the code check "has this expired?" and refresh it first if so.                                                                                    |

**All four columns are optional (nullable)** — most staff members will never
connect a Google account. Disconnecting clears all four back to null on the
same row (there's no separate "connection" row to soft-delete anymore).

**Uniqueness rule:** `google_email` must be unique — but a plain
`unique=True` (with `null=True`) is enough. Postgres allows any number of
`NULL`s under a unique constraint and disconnecting sets `google_email` back
to `null` rather than leaving a stale row behind, so there's no old value
left around to collide with a later reconnect.

---

## Table 2: `Appointment`

**File:** `appointments/models.py`

Once an appointment is mirrored onto Google Calendar, what Google gives back
is stored directly on that same appointment row. Nothing Appointment already
has (title, start/end time, notes, location) is repeated — only what Google
adds on top.

| New column         | Type            | What it stores                                                                 | Why we need it                                                                                      |
| ------------------ | --------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `google_event_id`  | Text (optional) | The ID Google assigned this event, e.g. `"abc123xyz"`                          | Needed to update (`patch_event`) or cancel (`delete_event`) this same event on Google's side later. |
| `google_meet_link` | URL (optional)  | The Google Meet video call link, e.g. `"https://meet.google.com/abc-defg-hij"` | So the app can show/send the meeting link to the staff member and the customer.                     |

**Both columns are optional (nullable)** — an appointment only gets these
values after it has actually been mirrored to Google.

**Uniqueness rule:** `google_event_id` must be unique — two appointments
should never point at the same Google event, or updating/cancelling one could
accidentally affect the other.

### No `google_participant_emails` column

Who gets invited to the Google event is **not** stored as its own column.
`Appointment.associate` is expected to hold more than one person (e.g. a
doctor and a health coach on the same appointment) and `Appointment.customer`
is always exactly one customer. So the invite list is always just "every
linked associate's Google email + the customer's email" — worked out at the
moment we call Google, not copied into a separate column that could go stale
(e.g. if an associate's Google email changes later, an old stored copy here
would still show the wrong one).

---

## Also intentionally left out

- No `sync_token` / `watch_channel_id` / `watch_channel_expiration` columns.
  These are for a "Google notifies us when something changes" feature that
  isn't built yet — add them only when that feature is actually being built.

## Current state

`integrations/models.py` is already empty and `integrations/google_calendar/`
(`tokens.py`, `db.py`, `views.py`) already reads/writes the `Associate`
columns listed above — none of the `Appointment` columns are wired into any
code path yet. **None of this runs until the columns actually exist** — the
code will hit `AttributeError` on a live `Associate`/`Appointment` row until
the migration below lands.

## Notes for whoever implements this

- Add the columns above to `accounts/associates/models.py` (and, once
  `insert_event`/`patch_event` are wired into appointment creation,
  `appointments/models.py`).
- The project owner generates and reviews the migration — do not run
  `makemigrations` automatically.
