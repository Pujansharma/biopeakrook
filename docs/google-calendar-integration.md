# Google Calendar Integration

Lets one designated shared Google account (e.g. `care@biopeak.health`,
`settings.GOOGLE_CALENDAR_ID`) get connected once, so every appointment
booked in this system shows up on that calendar too - with a Google Meet
link attached automatically. This is **not** a "each staff member connects
their own calendar" feature - `/complete/` only accepts the one configured
shared account, see "Identity" below.

**Status: connect/disconnect and event sync are both live.** Event sync
runs from the communication outbox worker (same book/cancel/reschedule
hooks as WhatsApp), not inline on the request. See "Event sync
(book/reschedule/cancel)" below.

---

## Why this exists

Today, an `Appointment` in this system only exists in our own database. Staff
don't get it on their phone/laptop calendar unless someone tells them by hand.
This integration mirrors every appointment onto one shared, connected Google
Calendar account, so anyone watching that calendar gets the normal Google
reminders and a video call link if the appointment needs one - regardless of
which associate(s) are actually assigned to it (they're added as attendees,
not organizers - see "Picking which calendar hosts the event" below).

## How it works, end to end

1. **Whoever administers the shared account clicks "Connect Google
   Calendar"** somewhere in the admin frontend. That takes them to a URL
   built by `build_auth_url()` - Google's own consent screen, asking "allow
   this app to manage your calendar events?" `/connect/` doesn't need to
   know who's connecting yet - see "Identity: how we know which user
   connected" below.
2. **They approve it, signed into the shared Google account**
   (`settings.GOOGLE_CALENDAR_ID`, e.g. `care@biopeak.health`) - not
   whichever personal Google account they happen to be signed into. Google
   redirects their browser back to us with a one-time code.
3. **We forward that code to the frontend**, unchanged - `/callback/` doesn't
   call Google or touch the database itself, it just redirects the browser
   to the admin frontend with `#code=...` (a URL fragment, not a query
   string, so it's never sent to the server and never lands in access/proxy
   logs or a `Referer` header).
4. **The frontend calls `/complete/`** (no JWT needed - this view never
   reads `request.user`), passing that same `code`. Only there do we trade
   the code for tokens using `exchange_code()` - Google gives us back an
   `access_token` (short-lived, ~1 hour) and a `refresh_token` (long-lived,
   doesn't expire until revoked).
5. **We check the connected account's own email** (`fetch_email()`) equals
   `settings.GOOGLE_CALENDAR_ID` - if not, `/complete/` 400s and nothing is
   saved. Only then do we look up which `User` gets the tokens, by matching
   that same email against `User.email` for an active platform `Admin` or
   `Associate` - see "Identity" below - and save the tokens, encrypted, onto
   that user's `GoogleCalendarConnection` row (see "Database columns" below).
6. **When an appointment is created/rescheduled/cancelled**, after the DB
   write commits we enqueue a Google Calendar row on `CommunicationOutbox`
   (same hook as WhatsApp). A wake worker / 10-minute sweep calls
   `insert_event()` / `patch_event()` / `delete_event()` and saves the
   Google event's ID + Meet link on `Appointment.google_event_id` /
   `google_meet_link` - see "Event sync" below. The book/cancel/reschedule
   request never calls Google.
7. **Before every Google API call**, `get_valid_access_token()` checks if the
   saved access token has expired - if so, it silently uses the refresh token
   to get a new one first. It re-reads the `GoogleCalendarConnection` row
   right before doing that refresh, so a concurrent book/reschedule/cancel
   that already refreshed and saved a live token wins instead of triggering
   a second, redundant refresh (Google can rotate/invalidate the refresh
   token on refresh, so two concurrent refreshes for the same connection is
   unsafe). If Google rejects the refresh token with HTTP 400 `invalid_grant`,
   `get_valid_access_token()` re-reads the row: if another worker already
   rotated `google_refresh_token`, it retries once instead of wiping. It
   only calls `db.clear_google_calendar_tokens()` when the token we sent is
   still the one stored (revoked/expired for real). The error is then
   re-raised and swallowed by the calling sync flow like any other
   `GOOGLE_SYNC_ERRORS` failure - so `get_fixed_calendar_organizer()` stops
   treating that connection as connected instead of every sync silently
   soft-failing until someone hits `/refresh/` or `/disconnect/` by hand.

## The files

All under `integrations/google_calendar/`:

| File                                                  | What it does                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `utils.py`                                            | Encrypt/decrypt for tokens before they touch the database. Reads the encryption key from Django settings and builds the Fernet cipher lazily on first use, so importing this module doesn't require the key to be configured.                                                                                      |
| `google_oauth.py`                                     | Talks to Google's _login_ side - builds the consent screen URL, trades codes for tokens, refreshes tokens, looks up the connected email, revokes access. Reads its own client ID/secret/redirect URL from Django settings, same pattern as `ORANGE_LABS_*` in `core/settings/{development,staging,production}.py`. |
| `calendar_api.py`                                     | Talks to Google's _calendar_ side - create/update/delete events on someone's calendar.                                                                                                                                                                                                                             |
| `tokens.py`                                           | The glue: given a `GoogleCalendarConnection`, hands back a token that's guaranteed to still be valid (refreshing it first if needed).                                                                                                                                                                              |
| `db.py`                                               | Persists a refreshed access/refresh token onto the `GoogleCalendarConnection` row via `save(update_fields=...)` - only the columns that changed, not a full-row save.                                                                                                                                              |
| `connections.py`                                      | Owner lookup: active `Admin` or `Associate` profile, the signed-in user's connection row, shared-organizer disconnect gate, `get_fixed_calendar_organizer()`.                                                                                                                                                      |
| `views.py`                                            | The six HTTP endpoints admin/associate staff hit: status, connect, callback, complete, disconnect, refresh. See below.                                                                                                                                                                                             |
| `urls.py`                                             | Routes those six views under `/google-calendar/`.                                                                                                                                                                                                                                                                  |
| `google_sync.py`                                      | Desired-state sync: match Google Calendar to the live `Appointment`. Called from the communication outbox worker (`process_google_outbox_message`), not from the book/cancel/reschedule request. See "Event sync (book/reschedule/cancel)" below.                                                                     |
| `appointments/utils/emails.py` (outside this package) | Builds the formatted event `description` text (`build_appointment_confirmed_notes()`/`build_appointment_rescheduled_notes()`) - patient/service plus a modality-conditional clinic address or Meet-link note. See "Event description" below.                                                                       |

Connection tokens live on `GoogleCalendarConnection` (`integrations/models.py`,
1:1 `User`). Mirrored event ids live on `Appointment` - see "Database columns"
below.

## Connect/disconnect/refresh endpoints

| Endpoint                              | Auth            | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /google-calendar/connect/`      | None (public)   | Returns Google's consent-screen URL as JSON (`{"data": {"auth_url": "..."}}`). No body needed - see "Identity" below for why. The frontend navigates the browser there itself.                                                                                                                                                                                                                                                                                                                                                                            |
| `GET /google-calendar/callback/`      | None (public)   | Google redirects the browser here after consent. Forwards `code` unchanged to `ADMIN_FRONTEND_URL` as `#code=...`, or `#connected=0&error=...` on a missing param. Raises a config error (`ImproperlyConfigured`) instead of redirecting if `ADMIN_FRONTEND_URL` isn't set. Does not touch the database.                                                                                                                                                                                                                                                  |
| `POST /google-calendar/complete/`     | None (public)   | Frontend calls this with the `code` it got from `/callback/`. Exchanges the code with Google and fetches the connected account's email - 400s immediately (`"This is not the shared Google Calendar account used for appointment sync..."`) unless that email case-insensitively equals `settings.GOOGLE_CALENDAR_ID`. Only then does it look up the active `User` whose login email matches **and** who has an active platform `Admin` or `Associate` profile, and saves the tokens onto that user's `GoogleCalendarConnection` (ORM-evict any other connection that stale-held the same `google_email`, then revoke those copied grants after commit). Unique-email race: if this user is already connected as that email, return 200 (the one-time `code` is already spent); else retry persist once; else 400. Returns `{"data": {"google_email": "...", "user_id": "..."}}` on success. |
| `DELETE /google-calendar/disconnect/` | Admin or Associate (JWT) | Revokes the token with Google and clears the signed-in user's own `google_access_token`/`google_refresh_token`/`google_access_token_expires_at`. `google_email` is deliberately kept as a "last connected as \_\_\_" record - check `google_refresh_token` to know if actually still connected. If the caller is the fixed shared calendar organizer (`google_email == settings.GOOGLE_CALENDAR_ID`), disconnecting kills sync for every center - platform `Admin` may disconnect; an associate must be `is_active` **and** hold `is_admin=True` on at least one active center assignment - 403 otherwise. |
| `POST /google-calendar/refresh/`      | Admin or Associate (JWT) | Forces a refresh of the signed-in user's own tokens right now via `google_oauth.refresh_access_token()`, regardless of whether the stored access token has actually expired - unlike the lazy, only-if-expired refresh `get_valid_access_token()` does internally before every Calendar API call. Requires `is_active` and a live `google_refresh_token` (same connected test as status). Saves the new `access_token`/`expires_at` (and `refresh_token`, if Google rotates it) via `update_google_calendar_tokens()`. |
| `GET /google-calendar/`               | Admin or Associate (JWT) | Returns `{"data": {"google_email": "...", "is_connected": true/false}}` for the signed-in user's `GoogleCalendarConnection` - `is_connected` is `connection.is_active` **and** `bool(connection.google_refresh_token)`, not just whether `google_email` is set (see the "last connected as \_\_\_" note above). Soft-off (`is_active=False`) matches `get_fixed_calendar_organizer()` skipping that row. Never exposes the token columns themselves. |

**Why `/connect/` doesn't redirect directly:** the callback (`/callback/`) is a
plain browser navigation triggered by Google - it can't carry our
`Authorization` header. So `/connect/` is a normal JSON endpoint the
frontend calls first; the frontend itself then sends the browser to the
returned `auth_url`.

**Why `/callback/` and `/complete/` stay separate.** `/callback/` is a
**plain browser redirect**, not a JSON API call - on failure it can only signal
`#connected=0&error=<code>` in a URL, never a real error body. Folding the
whole exchange (call Google's token endpoint, fetch the email, look up the
user, save to DB) into `/callback/` would mean every failure mode -
failed exchange, missing refresh token, no matching admin/staff user, a DB
integrity error - has to be squeezed into a URL-safe error code instead of
a proper JSON `detail` message. `/complete/` stays a normal `POST` the
frontend calls with `fetch`/`axios`, so it can return a real, specific JSON
error (e.g. "No active Biopeak admin or staff account uses this Google
account's email...") that the frontend can show directly. In a real frontend, `/callback/`
redirects to the frontend's own route with `code`, and the frontend's own
JS calls `/complete/` - the "copy code out of the address bar" step used
for manual Bruno testing is invisible once a real frontend exists.

**Identity: how we know which user connected.** Identity comes from
Google itself, never from anything the frontend sends - there's no
user/associate id passed to `/connect/` or `/complete/` for this. After
exchanging the code, `/complete/` calls `fetch_email()` to get the connected
account's own (Google-verified) email, and **first rejects it outright**
unless it case-insensitively equals `settings.GOOGLE_CALENDAR_ID` - the one
configured shared account (400: "This is not the shared Google Calendar
account used for appointment sync. Connect the configured shared account
instead."). This is not a per-user "connect your own calendar" flow;
only the one fixed shared account may ever hold tokens through this
endpoint. Only past that check does it look up the `User` whose
**login** email (`User.email`) matches that same email, requiring
`User.is_active` **and** an active platform `Admin` or `Associate` profile
(400: "No active Biopeak admin or staff account uses this Google account's
email..." otherwise) - `GoogleCalendarConnection.google_email` (the "you're
connected as \_\_\_" column) is a separate field that gets set to whatever
email that lookup matched. Whoever actually signs into Google on the
consent screen decides who gets the tokens - not whoever called
`/connect/` or `/complete/`, so there's no way for one user to mint a
consent link and have someone else's approval land tokens on the wrong
row. Practical effect: **whoever administers the shared Google account
must also be an active Biopeak Nexus admin or staff login with that same
email address** - if no active admin/associate login email matches
`GOOGLE_CALENDAR_ID`, connecting is impossible until one is created/updated
to match.

**Why there's no CSRF `state` param.** `/complete/` never reads
`request.user`, so there's no session-based action for a CSRF nonce to guard
against being triggered on someone else's behalf, and a valid `code` can
only exist if someone actually completed Google's own consent screen for
our registered `client_id` - Google's own client-secret-backed exchange
(`exchange_code()`) already guarantees that. A `state` nonce would only add
"was this `code` used within N minutes of a `/connect/` call," which isn't a
meaningful security boundary here, so `/connect/`, `/callback/`, and
`/complete/` don't generate, forward, or check one.

**Why the redirect never carries the connected email:** URL fragments and
query strings both end up in browser history, but query strings additionally
end up in proxy/CDN logs and the `Referer` header sent to the next page. Even
carried as a fragment, `/callback/`'s redirect only ever includes `code`
(opaque, single-use, expires in 10 minutes) or a `connected=0&error=...`
failure code - never the Google email. The frontend gets the email (and
which user it resolved to) from `/complete/`'s JSON response body
instead.

**Why `/disconnect/` takes no id in the URL:** it always acts on
the signed-in user's `GoogleCalendarConnection` - never a
client-supplied user/staff id - so one user can never disconnect
another's calendar. `/refresh/` follows the same rule for the same reason.

## Database columns

Tokens live on `GoogleCalendarConnection` (`integrations/models.py`, 1:1
`User` PK). Mirrored event ids live on `Appointment`. User owns the
migration that creates the connection table, copies any live Associate
google columns, then drops those Associate columns.

### `GoogleCalendarConnection` (`integrations/models.py`)

One row per `User`. In practice only the one login whose email matches
`settings.GOOGLE_CALENDAR_ID` will ever have tokens populated -
`/complete/` rejects any other Google account (see "Identity" above), so
this isn't a "each staff member connects their own calendar" table.

| Column                           | Type                   | What it stores                                                         | Why we need it                                                                                                                                               |
| -------------------------------- | ---------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `user`                           | OneToOne `User` (PK)   | The Biopeak login that owns this connection (`Admin` or `Associate`)   | Either account type can hold the shared calendar tokens. Distinct from center-admin `AssociateCenterAssignment.is_admin`.                                    |
| `google_email`                   | Email (optional)       | The connected Google account's email, e.g. `care@biopeak.health` (should match `settings.GOOGLE_CALENDAR_ID`) | Shown in the UI as "Connected as \_\_\_". Distinct from `user.email` (the login email) - this is the _connected Google_ account, which may differ.           |
| `google_access_token`            | Text (optional)        | An encrypted, short-lived Google access key (expires in about an hour) | Needed to make Google Calendar API calls on the owner's behalf. Encrypted before saving - never stored as plain text.                                        |
| `google_refresh_token`           | Text (optional)        | An encrypted, long-lived Google key that doesn't expire on its own     | Used to get a new `google_access_token` automatically once the old one expires, without asking the owner to reconnect. Encrypted before saving.              |
| `google_access_token_expires_at` | Date + time (optional) | When `google_access_token` stops working                               | Lets the code check "has this expired?" and refresh it first if so.                                                                                          |

All four google columns are optional (nullable). Disconnecting only clears
the three token columns back to null - `google_email` is deliberately left
in place as a record of the last-connected account (see "Why `/disconnect/`
..." above for why anything checking "is this user connected" must test
`connection.is_active` **and** `google_refresh_token`, not `google_email`).

**Uniqueness:** `google_email` must be unique, case-insensitively -
`models.UniqueConstraint(Lower("google_email"), ...)`
(`integrations/models.py`), not a plain `unique=True`, since two emails that
only differ by case are still the same Google account; lookups against it
use `__iexact` throughout. Postgres allows any number of `NULL`s under the
constraint either way. Because disconnect leaves `google_email` in place, a
later reconnect by a _different_ user to the same Google account is handled
at connect time instead: `GoogleCalendarCompleteView` proactively evicts
whichever other connection currently holds that `google_email` - unlike a
self-disconnect, this eviction **does** clear the evicted row's
`google_email` too (all four columns), since the new connection is about to
be saved with that same `google_email` value and the old row must give it
up first. Evict copies the stale row's refresh token, then ORM-clears
that row and saves the new connection inside `transaction.atomic()`.
Revoke of those copied grants runs **after** commit so a rollback cannot
leave Google dead while local tokens still look connected. `InvalidToken`
or Google HTTP failure on that post-commit revoke is logged and ignored
(local columns are already cleared). If `connection.save()` hits the
unique-email `IntegrityError`, `/complete/` re-reads: this user already
connected as that email → 200 (OAuth `code` is one-time and already
spent); else retry persist once; still colliding → 400.

### `Appointment` (`appointments/models.py`)

Once an appointment is mirrored onto Google Calendar, what Google gives back
is stored directly on that same appointment row.

| Column             | Type            | What it stores                                                                           | Why we need it                                                                                                                                                                                |
| ------------------ | --------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `notes`            | Text (optional) | Free-text notes for the appointment, e.g. `"First visit"`. Settable via book/reschedule. | Appended to the formatted event `description` built by `appointments/utils/emails.py` (see "Event description" below). Independent of Google - kept even if the appointment was never synced. |
| `google_event_id`  | Text (optional) | The ID Google assigned this event, e.g. `"abc123xyz"`                                    | Needed to update (`patch_event`) or cancel (`delete_event`) this same event on Google's side later.                                                                                           |
| `google_meet_link` | URL (optional)  | The Google Meet video call link, e.g. `"https://meet.google.com/abc-defg-hij"`           | So the app can show/send the meeting link to the staff member and the customer.                                                                                                               |

All three columns are optional. `google_event_id`/`google_meet_link` only
get a value once the appointment has actually been mirrored to Google. The
event's `summary` (title) isn't stored at all - it's a fixed string built
fresh at sync time (see "Event sync" below), so there's no separate column
for it to go stale in.

**Uniqueness:** `google_event_id` must be unique - two appointments should
never point at the same Google event, or updating/cancelling one could
accidentally affect the other.

**No `google_participant_emails` column.** Who gets invited is not stored
as its own column. An appointment can carry several associates via
`AppointmentAssociate` (`associate_links`) - a doctor, a health coach, a
whole `CenterCareTeam` - plus exactly one customer. The invite list is
always worked out fresh at the moment we call Google (every linked
associate's login `email` plus the customer's `contact_email`), not copied
into a column that could go stale - e.g. if an associate's Google email
changes later, a stored copy here would still show the wrong one. Who
_hosts_ the event is a separate question from who's invited, and isn't tied
to the assigned associates at all - see "Picking which calendar hosts the
event" below.

**Also intentionally left out:** no `sync_token` / `watch_channel_id` /
`watch_channel_expiration` columns - those are for a "Google notifies us
when something changes" feature that isn't built yet.

## Event sync (book/reschedule/cancel)

Sync is best-effort and **asynchronous**. Book / cancel / reschedule enqueue
WhatsApp + Google Calendar rows on `CommunicationOutbox` via
`schedule_queue_*` (`transaction.on_commit`). The request never calls Google.
**A Google Calendar failure must never block, fail, or roll back an
appointment operation in Biopeak Nexus.**

Worker: `uv run manage.py process_communication_outbox` (wake on insert +
10-minute sweep). `process_google_outbox_message` calls
`sync_appointment_with_google()` in `integrations/google_calendar/google_sync.py`.
That function **desired-states** from the live appointment (not a replay of
queued event types): cancelled → `delete_event`; otherwise insert/patch.
Google event `id` is the appointment UUID hex so retries are idempotent
(HTTP 409 → get + patch). Max 2 attempts. Stale Google `SENDING` retries;
stale WhatsApp `SENDING` is skipped. One open Google row per appointment
(coalesce). Wake publishes one SQS message per enqueue that has work, not
per row. `google_meet_link` may be null on the book 201 until the worker
runs.

`GOOGLE_SYNC_ERRORS` (`requests.RequestException`, `ValueError`,
`InvalidToken`, `ImproperlyConfigured`) fail the outbox row (retry once,
then skip). Organizer disconnected is retryable `FAILED`. Persist of
`google_event_id` / `google_meet_link` swallowing `DatabaseError` is
unchanged — deterministic event id still lets the next run patch/delete.

**Picking which calendar hosts the event.** Every appointment's Google
Calendar event is created on **one single shared account** -
`settings.GOOGLE_CALENDAR_ID` (env var `{DEV,STG,PRD}_GOOGLE_CALENDAR_ID`,
e.g. `care@biopeak.health`) - via `get_fixed_calendar_organizer()`, regardless
of which associate is assigned to the appointment. That fixed account still
has to go through the normal `/google-calendar/connect/` + `/complete/` flow
- its tokens live on the one `GoogleCalendarConnection` row whose
`google_email` (the connected-Google-account column) matches
`GOOGLE_CALENDAR_ID` (`/complete/` rejects any other Google account
outright, see "Identity" above). `get_fixed_calendar_organizer()` filters
that connection on `is_active=True`, `user__is_active=True`, and an active
`Admin` or `Associate` profile, and separately checks a live
`google_refresh_token` - `google_email` alone can be stale (disconnect
deliberately keeps it, see the "Disconnect" section below), and treating a
stale match as "connected" would hard-fail every booking instead of
gracefully skipping sync. Returns `None` ("proceed unsynced") if the setting
is unset, no active admin/staff connection has that email, or that owner
has since disconnected - only an actual Google API failure with a genuinely
connected fixed account blocks the write. Because that same connection is
the one gate for org-wide sync, `/disconnect/` refuses to let an associate
disconnect it unless they are `is_active` and also hold `is_admin=True` on
an active center assignment; a platform `Admin` may disconnect it (see
"Disconnect" above).

**Attendees are unaffected by this change** - assigned associates (doctor,
health coach, care team) are invited as ordinary Google Calendar attendees,
resolved from the appointment's saved `associate_links` at worker time; only
who _owns and hosts_ the event is the fixed organizer. Attendee list = the
customer's `contact_email` plus those associates' login `email` (the fixed
organizer itself is excluded if it is also assigned).

**On book** - worker `insert_event()` with deterministic id, `need_meet_link=True`
only when `modality` is `virtual`. Title `"Appointment Confirmed"`.

**On reschedule** - title `"Appointment Rescheduled"`. Patch existing id;
404/410 → insert. `add_meet_link` only when virtual and no Meet link yet.
`clear_meet_link` when leaving virtual.

**On cancel** - worker `delete_event()` (404/410 already success). Does
**not** clear `google_event_id` / `google_meet_link` — historical record.

## Event description

The Google event's `description` isn't the raw `notes` field a caller
passes in - it's a formatted message built by
`appointments/utils/emails.py` (`build_appointment_confirmed_notes()` for
book, `build_appointment_rescheduled_notes()` for reschedule) and only then
handed to `sync_*_appointment_with_google()` as `notes`. Both functions
share the same shape: a greeting with the patient's name, then a
`<b>Service:</b>` line (Google Calendar's own UI renders a handful of basic
tags like `<b>` in the description), a location line, a closing note, and
finally the caller-supplied `notes` text (if any) appended by
`append_notes()`. There is no date/time line - the event's own start/end
times already show that on the calendar entry itself.
`appointments/utils/emails.py` also defines `get_appointment_date()` /
`get_appointment_time()` helpers, but neither is called from anywhere -
they were built for a date/time line that isn't in the message.

**The location line is modality-conditional** (`build_location_note()`):

- `modality == AppointmentModes.VIRTUAL` - shows a one-line "join using the
  Google Meet link on the calendar invite" note. No clinic address. The
  actual Meet link isn't inlined into this text (it doesn't exist yet at the
  point the description is built for a new event) - Google attaches it to
  the event itself via `conferenceData`/`hangoutLink` (see
  `need_meet_link`/`add_meet_link` above), and shows it as a join button on
  the calendar entry.
- Anything else (`in_person`, `both`) - shows `<b>Clinic Address:</b>`
  followed by `Center.full_address` (`accounts/centers/models.py`).

`cancel` has no equivalent - `sync_cancelled_appointment_with_google()`
only calls `delete_event()`, which doesn't touch `description`.

**Every user-controlled piece of this text is HTML-escaped first**
(`html.escape()`) - patient name, service name, and clinic address in
`build_appointment_confirmed_notes()`/`build_appointment_rescheduled_notes()`/
`build_location_note()`, and the caller-supplied `notes` in `append_notes()`.
Since Google Calendar's UI actually renders a handful of tags (`<b>` among
them) from `description`, an unescaped patient name like
`<script>...</script>` or an unescaped `notes` value containing `<b>` could
otherwise break the intended formatting or inject markup into what everyone
on the invite sees - only the literal `<b>...</b>` tags this code itself
writes are meant to render as markup.

## Rescheduling and Meet links

`patch_event()` takes `add_meet_link`, not `need_meet_link` - and it must only
be passed `True` the first time a Meet link is being added to an event.
Passing it `True` on an event that already has one sends Google a fresh
`conferenceData.createRequest`, which creates a brand new conference and
rotates the Meet link, stranding anyone holding the old one. That's exactly
why `sync_rescheduled_appointment_with_google()` gates it on
`not instance.google_meet_link` - it must flip to `True` only the first
time a link is added, never on a reschedule that already has one.

`patch_event()` also takes `clear_meet_link` (mutually exclusive with
`add_meet_link`) - `sync_rescheduled_appointment_with_google()` passes it
`True` when the appointment already has a `google_meet_link` **and** the
(possibly just-changed) `modality` is no longer `virtual`, so an appointment
rescheduled away from virtual drops its Meet link instead of leaving a stale
one on the Google event. Google only removes conference data when
`conferenceData` is sent as an explicit `null` in the PATCH body - not an
empty object - so that's exactly what `clear_meet_link=True` sends
(`body["conferenceData"] = None` in `calendar_api.patch_event()`).

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
