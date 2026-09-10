# Google Calendar Integration

Lets one designated shared Google account (e.g. `care@biopeak.health`,
`settings.GOOGLE_CALENDAR_ID`) get connected once, so every appointment
booked in this system shows up on that calendar too - with a Google Meet
link attached automatically. This is **not** a "each staff member connects
their own calendar" feature - `/complete/` only accepts the one configured
shared account, see "Identity" below.

**Status: connect/disconnect and event sync are both live.** The
status/connect/callback/complete/disconnect/refresh endpoints, Google API
client, and the database columns they need (see "Database columns" below)
are all in place and migrated. `insert_event()`/`patch_event()`/`delete_event()` are
wired into appointment book/reschedule/cancel (sync helpers in
`integrations/google_calendar/google_sync.py`) - see "Event sync
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
   know who's connecting yet - see "Identity: how we know which associate
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
   saved. Only then do we look up which `Associate` gets the tokens, by
   matching that same email against `Associate.user.email` - see "Identity"
   below - and save the tokens, encrypted, onto that row (see "Database
   columns" below).
6. **When an appointment is created/rescheduled/cancelled**, after the DB
   write for that operation succeeds, we call `insert_event()` /
   `patch_event()` / `delete_event()` to create, update, or delete the
   matching event on the fixed calendar account, and save the Google event's
   ID + Meet link on the `Appointment` row's `google_event_id` /
   `google_meet_link` columns - see "Event sync" below.
7. **Before every Google API call**, `get_valid_access_token()` checks if the
   saved access token has expired - if so, it silently uses the refresh token
   to get a new one first. It re-reads the associate row right before doing
   that refresh, so a concurrent book/reschedule/cancel that already
   refreshed and saved a live token wins instead of triggering a second,
   redundant refresh (Google can rotate/invalidate the refresh token on
   refresh, so two concurrent refreshes for the same associate is unsafe).
   If Google rejects the refresh token outright (HTTP 400, `invalid_grant`
   - revoked, expired, or rotated away), the stored tokens are cleared via
   `db.clear_associate_google_tokens()` (same helper `/refresh/` and
   `/disconnect/` use) before the error is re-raised and swallowed by the
   calling sync flow like any other `GOOGLE_SYNC_ERRORS` failure - so
   `get_fixed_calendar_organizer()` stops treating that associate as
   connected instead of every sync silently soft-failing until someone
   hits `/refresh/` or `/disconnect/` by hand.

## The files

All under `integrations/google_calendar/`:

| File                                                  | What it does                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `utils.py`                                            | Encrypt/decrypt for tokens before they touch the database. Reads the encryption key from Django settings and builds the Fernet cipher lazily on first use, so importing this module doesn't require the key to be configured.                                                                                      |
| `google_oauth.py`                                     | Talks to Google's _login_ side - builds the consent screen URL, trades codes for tokens, refreshes tokens, looks up the connected email, revokes access. Reads its own client ID/secret/redirect URL from Django settings, same pattern as `ORANGE_LABS_*` in `core/settings/{development,staging,production}.py`. |
| `calendar_api.py`                                     | Talks to Google's _calendar_ side - create/update/delete events on someone's calendar.                                                                                                                                                                                                                             |
| `tokens.py`                                           | The glue: given an associate, hands back a token that's guaranteed to still be valid (refreshing it first if needed).                                                                                                                                                                                              |
| `db.py`                                               | Persists a refreshed access/refresh token onto the `Associate` row via `save(update_fields=...)` - only the columns that changed, not a full-row save.                                                                                                                                                             |
| `views.py`                                            | The six HTTP endpoints associates actually hit: status, connect, callback, complete, disconnect, refresh. See below.                                                                                                                                                                                               |
| `urls.py`                                             | Routes those six views under `/google-calendar/`.                                                                                                                                                                                                                                                                  |
| `google_sync.py`                                      | The appointment-side wiring: picks the fixed calendar organizer and syncs a booked/rescheduled/cancelled `Appointment` to Google Calendar. Called from `appointments/serializers/booking.py`. See "Event sync (book/reschedule/cancel)" below.                                                                     |
| `appointments/utils/emails.py` (outside this package) | Builds the formatted event `description` text (`build_appointment_confirmed_notes()`/`build_appointment_rescheduled_notes()`) - patient/service plus a modality-conditional clinic address or Meet-link note. See "Event description" below.                                                                       |

`integrations/models.py` is empty - this feature doesn't get its own tables.
Connection/event data lives directly on `Associate` and `Appointment` - see
"Database columns" below.

## Connect/disconnect/refresh endpoints

| Endpoint                              | Auth            | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------- | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /google-calendar/connect/`      | None (public)   | Returns Google's consent-screen URL as JSON (`{"data": {"auth_url": "..."}}`). No body needed - see "Identity" below for why. The frontend navigates the browser there itself.                                                                                                                                                                                                                                                                                                                                                                            |
| `GET /google-calendar/callback/`      | None (public)   | Google redirects the browser here after consent. Forwards `code` unchanged to `ADMIN_FRONTEND_URL` as `#code=...`, or `#connected=0&error=...` on a missing param. Raises a config error (`ImproperlyConfigured`) instead of redirecting if `ADMIN_FRONTEND_URL` isn't set. Does not touch the database.                                                                                                                                                                                                                                                  |
| `POST /google-calendar/complete/`     | None (public)   | Frontend calls this with the `code` it got from `/callback/`. Exchanges the code with Google and fetches the connected account's email - 400s immediately (`"This is not the shared Google Calendar account used for appointment sync..."`) unless that email case-insensitively equals `settings.GOOGLE_CALENDAR_ID`. Only then does it look up the active `Associate`/`User` whose login email matches, and saves the tokens onto that row (evicting any other associate that stale-held the same `google_email` first). Returns `{"data": {"google_email": "...", "associate_id": "..."}}` on success.                                                                                                                                                                                                                                                               |
| `DELETE /google-calendar/disconnect/` | Associate (JWT) | Revokes the token with Google and clears the signed-in associate's own `google_access_token`/`google_refresh_token`/`google_access_token_expires_at`. `google_email` is deliberately kept as a "last connected as \_\_\_" record - check `google_refresh_token` to know if actually still connected. If the caller is the fixed shared calendar organizer (`google_email == settings.GOOGLE_CALENDAR_ID`), this requires the caller to be `is_active` **and** hold `is_admin=True` on at least one active center assignment, since disconnecting that account kills sync for every center - 403 otherwise. |
| `POST /google-calendar/refresh/`      | Associate (JWT) | Forces a refresh of the signed-in associate's own tokens right now via `google_oauth.refresh_access_token()`, regardless of whether the stored access token has actually expired - unlike the lazy, only-if-expired refresh `get_valid_access_token()` does internally before every Calendar API call. Saves the new `access_token`/`expires_at` (and `refresh_token`, if Google rotates it) via `update_associate_google_tokens()`.                                                                                                                      |
| `GET /google-calendar/`               | Associate (JWT) | Returns `{"data": {"google_email": "...", "is_connected": true/false}}` for the signed-in associate - `is_connected` is `bool(associate.google_refresh_token)`, not just whether `google_email` is set (see the "last connected as \_\_\_" note above). Never exposes the token columns themselves.                                                                                                                                                                                                                                                          |

**Why `/connect/` doesn't redirect directly:** the callback (`/callback/`) is a
plain browser navigation triggered by Google - it can't carry our
`Authorization` header. So `/connect/` is a normal JSON endpoint the
frontend calls first; the frontend itself then sends the browser to the
returned `auth_url`.

**Why `/callback/` and `/complete/` stay separate.** `/callback/` is a
**plain browser redirect**, not a JSON API call - on failure it can only signal
`#connected=0&error=<code>` in a URL, never a real error body. Folding the
whole exchange (call Google's token endpoint, fetch the email, look up the
associate, save to DB) into `/callback/` would mean every failure mode -
failed exchange, missing refresh token, no matching associate, a DB
integrity error - has to be squeezed into a URL-safe error code instead of
a proper JSON `detail` message. `/complete/` stays a normal `POST` the
frontend calls with `fetch`/`axios`, so it can return a real, specific JSON
error (e.g. "No active Biopeak Staff account uses this Google account's
email...") that the frontend can show directly. In a real frontend, `/callback/`
redirects to the frontend's own route with `code`, and the frontend's own
JS calls `/complete/` - the "copy code out of the address bar" step used
for manual Bruno testing is invisible once a real frontend exists.

**Identity: how we know which associate connected.** Identity comes from
Google itself, never from anything the frontend sends - there's no
associate/user id passed to `/connect/` or `/complete/` for this. After
exchanging the code, `/complete/` calls `fetch_email()` to get the connected
account's own (Google-verified) email, and **first rejects it outright**
unless it case-insensitively equals `settings.GOOGLE_CALENDAR_ID` - the one
configured shared account (400: "This is not the shared Google Calendar
account used for appointment sync. Connect the configured shared account
instead."). This is not a per-associate "connect your own calendar" flow;
only the one fixed shared account may ever hold tokens through this
endpoint. Only past that check does it look up the `Associate` whose
**login** email (`Associate.user.email`) matches that same email, requiring
`Associate.is_active` **and** `User.is_active` (400: "No active Biopeak
Staff account uses this Google account's email..." otherwise) -
`associate.google_email` (the "you're connected as \_\_\_" column) is a
separate field that gets set to whatever email that lookup matched. Whoever
actually signs into Google on the consent screen decides who gets the
tokens - not whoever called `/connect/` or `/complete/`, so there's no way
for one associate to mint a consent link and have someone else's approval
land tokens on the wrong row. Practical effect: **whoever administers the
shared Google account must also be an active Biopeak Nexus staff login with
that same email address** - if no active associate's login email matches
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
which associate it resolved to) from `/complete/`'s JSON response body
instead.

**Why `/disconnect/` takes no id in the URL:** it always acts on
`request.user.associate`, the associate the JWT belongs to - never a
client-supplied associate/staff id - so one associate can never disconnect
another's calendar. `/refresh/` follows the same rule for the same reason.

## Database columns

No dedicated tables - Google Calendar sync adds a handful of columns to two
tables that already exist: `Associate` (connection: email, tokens, expiry)
and `Appointment` (notes, and the mirrored event's Google event id + Meet
link). All seven are declared (`accounts/associates/models.py`,
`appointments/models.py`) and migrated -
`accounts/associates/migrations/0018_associate_email_associate_google_access_token_and_more.py`
and `appointments/migrations/0016_appointment_google_event_id_and_more.py`.

### `Associate` (`accounts/associates/models.py`)

These columns exist on every `Associate`, but in practice only the one
associate whose login email matches `settings.GOOGLE_CALENDAR_ID` will ever
have them populated - `/complete/` rejects any other Google account (see
"Identity" above), so this isn't a "each staff member connects their own
calendar" set of columns despite living on every associate's row.

| Column                           | Type                   | What it stores                                                         | Why we need it                                                                                                                                               |
| -------------------------------- | ---------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `google_email`                   | Email (optional)       | The connected Google account's email, e.g. `care@biopeak.health` (should match `settings.GOOGLE_CALENDAR_ID`) | Shown in the UI as "Connected as \_\_\_". Distinct from `associate.user.email` (the login email) - this is the _connected Google_ account, which may differ. |
| `google_access_token`            | Text (optional)        | An encrypted, short-lived Google access key (expires in about an hour) | Needed to make Google Calendar API calls on the staff member's behalf. Encrypted before saving - never stored as plain text.                                 |
| `google_refresh_token`           | Text (optional)        | An encrypted, long-lived Google key that doesn't expire on its own     | Used to get a new `google_access_token` automatically once the old one expires, without asking the staff member to reconnect. Encrypted before saving.       |
| `google_access_token_expires_at` | Date + time (optional) | When `google_access_token` stops working                               | Lets the code check "has this expired?" and refresh it first if so.                                                                                          |

All four columns are optional (nullable) - most staff members will never
connect a Google account. Disconnecting only clears the three token columns
back to null - `google_email` is deliberately left in place as a record of
the last-connected account (see "Why `/disconnect/` ..." above for why
anything checking "is this associate connected" must test
`google_refresh_token`, not `google_email`).

**Uniqueness:** `google_email` must be unique, case-insensitively -
`models.UniqueConstraint(Lower("google_email"), ...)`
(`accounts/associates/models.py`), not a plain `unique=True`, since two
emails that only differ by case are still the same Google account; lookups
against it use `__iexact` throughout. Postgres allows any number of `NULL`s
under the constraint either way. Because disconnect leaves `google_email` in
place, a later reconnect by a _different_ associate to the same Google
account is handled at connect time instead: `GoogleCalendarCompleteView`
proactively evicts whichever other associate currently holds that
`google_email` - unlike a self-disconnect, this eviction **does** clear the
evicted associate's `google_email` too (all four columns), since the new
associate is about to be saved with that same `google_email` value and the
old row must give it up first. The evict-then-save runs inside one
`transaction.atomic()` block, and the final `associate.save()` is still
wrapped in `try/except IntegrityError` (400) to cover a race between two
concurrent `/complete/` calls resolving to the same account.

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

Sync is best-effort: a Google Calendar outage, misconfiguration, or any
other API failure is logged and swallowed, and the appointment create/
reschedule/cancel proceeds exactly as if nothing was synced. **A Google
Calendar failure must never block, fail, or roll back an appointment
operation in Biopeak Nexus.** This applies the same way whether there's no
connected organizer at all, or a connected organizer whose API call fails -
either way, sync is skipped and the appointment write stands.

Code: `integrations/google_calendar/google_sync.py` -
`sync_new_appointment_with_google()`, `sync_rescheduled_appointment_with_google()`,
`sync_cancelled_appointment_with_google()`, called from
`appointments/serializers/booking.py` (`AppointmentBookSerializer.create`,
`AppointmentRescheduleSerializer.update`, `AppointmentCancelSerializer.update`)
through `transaction.on_commit(...)`, registered inside each operation's
`transaction.atomic()` block but only actually run once that block has
committed - a booking/reschedule/cancel rejected by the database (an
overlap, an idempotency conflict) never reaches Google at all, and the DB
connection isn't held open for the duration of the Google HTTP call. Book
and reschedule go through a module-level `sync_*_appointment_and_save()`
wrapper in `booking.py` that also persists the returned
`google_event_id`/`google_meet_link` onto the row in a follow-up
`save(update_fields=...)`. Cancel has no such wrapper - `transaction.on_commit(...)`
calls `sync_cancelled_appointment_with_google()` directly (via
`functools.partial`), since cancel never needs to persist anything new (see
"On cancel" below).
Each function catches `GOOGLE_SYNC_ERRORS` (`requests.RequestException`,
`ValueError`, `InvalidToken`, `ImproperlyConfigured`) plus an unrecovered
`requests.HTTPError` internally, logs via `core.utils.log.logger`, and
returns a "no sync happened" result instead of raising - `(None, None)`
for create, the untouched `(instance.google_event_id, instance.google_meet_link)`
for reschedule, and `False` for cancel. Nothing about the appointment write
itself is skipped or rolled back. If the Google call succeeds but the
follow-up `appointment.save(update_fields=[...])` in
`sync_new_appointment_and_save()`/`sync_rescheduled_appointment_and_save()`
(`booking.py`) then fails with a `DatabaseError`, that's logged
(`logger.warning`) and swallowed too - by design, the Google event is
**not** deleted to compensate, so it can end up existing on the calendar
with no `google_event_id` pointer in our DB in that (rare) case.

**Picking which calendar hosts the event.** Every appointment's Google
Calendar event is created on **one single shared account** -
`settings.GOOGLE_CALENDAR_ID` (env var `{DEV,STG,PRD}_GOOGLE_CALENDAR_ID`,
e.g. `care@biopeak.health`) - via `get_fixed_calendar_organizer()`, regardless
of which associate is assigned to the appointment. That fixed account still
has to go through the normal `/google-calendar/connect/` + `/complete/` flow
- its tokens live on the one `Associate` row whose `google_email` (the
connected-Google-account column) matches `GOOGLE_CALENDAR_ID` (`/complete/`
rejects any other Google account outright, see "Identity" above).
`get_fixed_calendar_organizer()` filters that `Associate` on `is_active=True`
and `user__is_active=True` too, and separately checks a live
`google_refresh_token` - `google_email` alone can be stale (disconnect
deliberately keeps it, see the "Disconnect" section below), and treating a
stale match as "connected" would hard-fail every booking instead of
gracefully skipping sync. Returns `None` ("proceed unsynced") if the setting
is unset, no active associate has that email, or that associate has since
disconnected - only an actual Google API failure with a genuinely connected
fixed account blocks the write. Because that same associate row is the one
gate for org-wide sync, `/disconnect/` refuses to let it disconnect itself
unless the caller is `is_active` and also holds `is_admin=True` on an active
center assignment (see "Disconnect" above).

**Attendees are unaffected by this change** - the appointment's actual
assigned associates (doctor, health coach, care team) are still invited as
ordinary Google Calendar attendees, resolved per-call from the _current_
`associates_payload` (book/reschedule) or the appointment's saved
`associate_links` (cancel, since associates aren't changing there); only who
_owns and hosts_ the event changed. Attendee list = the customer's
`contact_email` plus the login `email` of every one of those associates
(the fixed organizer itself is excluded if it happens to also be one of
them).

**On book** (`sync_new_appointment_with_google`) - `insert_event()` on the
organizer's calendar, _after_ the `Appointment` row is created and that
transaction has committed (via `transaction.on_commit(...)`), so a booking
rejected by the DB (e.g. an overlap or idempotency conflict) never creates a
Google event that would otherwise be orphaned. `need_meet_link=True` only
when `modality` is `virtual`. Returns
`(google_event_id, google_meet_link)`, which the caller saves onto the row
in a follow-up save right after. The event title is the fixed string
`"Appointment Confirmed"` - it does not include the service name or
appointment code.

**On reschedule** (`sync_rescheduled_appointment_with_google`) - event title
is the fixed string `"Appointment Rescheduled"` (also no service name/code).
If the appointment has no `google_event_id` yet (e.g. the fixed account was
connected _after_ the original booking), it creates a fresh event.
Otherwise `patch_event()` updates the existing event's time/room/attendees.
`add_meet_link` is `True` only when the appointment doesn't already have a
`google_meet_link` **and** the (possibly just-changed on this same
reschedule) `modality` is `virtual` - e.g. an in-person appointment
rescheduled to virtual picks up a Meet link it never had. If a Meet link
already exists, it's always left alone (`add_meet_link=False`) - reschedules
never rotate an existing Meet link. If Google returns 404/410 (the event no longer exists on the fixed
account's calendar - e.g. someone deleted it by hand directly in Google
Calendar, or the shared account was disconnected and a different Google
account connected under the same `GOOGLE_CALENDAR_ID` email since), a fresh
event is created in the same call instead of failing the reschedule. Called
_after_ the reschedule's own DB writes have committed (via
`transaction.on_commit(...)`), so a rejected reschedule (e.g. an overlap)
never touches Google at all. Returns `(google_event_id, google_meet_link)`
for the caller to persist in a small follow-up save.

**On cancel** (`sync_cancelled_appointment_with_google`) - `delete_event()`
using the fixed organizer, called _after_ the cancellation's own DB writes
have committed (via `transaction.on_commit(...)`), so a rejected cancel
never deletes a still-live Google event. Returns a plain `bool` and
deliberately does **not** touch `instance.google_event_id`/
`instance.google_meet_link` at all, even on a successful delete - those
two columns are kept on a cancelled appointment as a record of what was
synced, now pointing at a Google event that no longer exists after a
successful delete. A delete failure (or a disconnected organizer) is
surfaced via `logger.error` (not just a warning) so ops can find and clean
up the orphaned Google event by hand. No-ops (returns `False`, nothing to
raise) if the appointment was never synced.

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
