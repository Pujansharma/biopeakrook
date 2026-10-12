# Google Calendar Integration

Lets one designated shared Google account (e.g. `care@biopeak.health`,
`settings.GOOGLE_CALENDAR_ID`) get connected once, so every appointment
booked in this system shows up on that calendar too - with a Google Meet
link attached automatically. This is **not** a "each staff member connects
their own calendar" feature - `/callback/` only accepts the one configured
shared account for this flow, see "Identity" below.

**Status: connect/disconnect and event sync are both live.** Event sync
runs from the communication outbox worker (same book/cancel/reschedule
hooks as WhatsApp), not inline on the request. See "Event sync
(book/reschedule/cancel)" below.

**A second, separate feature lives in this same package: personal calendar
connect + availability sync.** Any signed-in Admin or Associate can connect
their _own_ personal Google Calendar (not the shared organizer account
above) from Settings, then pull their own busy events into Biopeak as
`AssociateAvailabilityBlock` rows - so a break or recurring lunch added
directly in someone's personal Google Calendar also blocks that time in
Biopeak. Today this is one-way in practice (Google → Biopeak, the code never
writes to a personal calendar) though the OAuth grant itself includes write
access too, kept available for a later write-back feature - see "Scope"
under "Personal calendar connect & availability sync" below.

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
3. **`/callback/` does the whole exchange itself, right there** - no
   separate frontend round trip. It unsigns `state`
   (`google_oauth.unsign_oauth_state()`, see "Routing two flows through one
   OAuth app" below) to learn which flow this is, trades the code for
   tokens using `exchange_code()` (Google gives back an `access_token`,
   short-lived ~1 hour, and a `refresh_token`, long-lived until revoked),
   and fetches the connected account's own email (`fetch_email()`).
4. **We check that email equals `settings.GOOGLE_CALENDAR_ID`** - if not,
   nothing is saved and the browser is redirected straight back to the
   frontend with an error flag (see step 6). Only past that check do we
   look up which `User` gets the tokens, by matching that same email
   against `User.email` for an active platform `Admin` or `Associate` - see
   "Identity" below - and save the tokens, encrypted, onto that user's
   `GoogleCalendarConnection` row (see "Database columns" below).
5. **`/callback/` redirects to the frontend one last time**, now carrying
   only a plain outcome flag - `#gcal_connected=1` on success, or
   `#gcal_error=<message>` on any failure along the way (denied consent,
   expired/tampered `state`, failed exchange, wrong account, no matching
   admin/staff login). Never the raw code, never the tokens, never the
   connected email itself - see "Why the redirect never carries the
   connected email" below. The frontend's only job at this point is to show
   a toast and re-fetch its status query.
6. **When an appointment is created/rescheduled/cancelled**, after the DB
   write commits we enqueue a Google Calendar row on `CommunicationOutbox`
   (same hook as WhatsApp). A wake worker / 15-minute sweep calls
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
   only calls `db.deactivate_google_calendar_connection()` when the token we
   sent is still the one stored (revoked/expired for real) - this flips
   `is_active` to `False` and leaves the token/email columns as they were,
   see "Database columns" below. The error is then
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
| `views.py`                                            | The HTTP endpoints admin/associate staff (and Google's own redirect) hit: status, connect, callback, disconnect, refresh, personal/connect. `/callback/` alone does the whole token exchange + save for both connect flows now - see below.                                                                        |
| `urls.py`                                             | Routes those views under `/google-calendar/`.                                                                                                                                                                                                                                                                      |
| `google_sync.py`                                      | Desired-state sync: match Google Calendar to the live `Appointment`. Called from the communication outbox worker (`process_google_outbox_message`), not from the book/cancel/reschedule request. See "Event sync (book/reschedule/cancel)" below.                                                                  |
| `availability_sync.py`                                | Desired-state sync: match a personal calendar's busy events to that user's `AssociateAvailabilityBlock` rows. Called manually from `/sync/` and automatically from the webhook below. See "Personal calendar connect & availability sync" below.                                                                   |
| `webhook_channel.py`                                  | Google push-notification channel lifecycle: register (`start_watch_channel`), stop (`stop_watch_channel`), self-heal/renew (`ensure_watch_channel_active`), and match an incoming notification to a connection. See "Personal calendar webhook (push notifications)" below.                                        |
| `appointments/utils/emails.py` (outside this package) | Builds the formatted event `description` text (`build_appointment_confirmed_notes()`/`build_appointment_rescheduled_notes()`) - patient/service plus a modality-conditional clinic address or Meet-link note. See "Event description" below.                                                                       |

Connection tokens live on `GoogleCalendarConnection` (`integrations/models.py`,
1:1 `User`). Mirrored event ids live on `Appointment` - see "Database columns"
below.

## Connect/disconnect/refresh endpoints

| Endpoint                              | Auth                     | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /google-calendar/connect/`      | None (public)            | Returns Google's consent-screen URL as JSON (`{"data": {"auth_url": "..."}}`). No body needed - see "Identity" below for why. The frontend navigates the browser there itself.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `GET /google-calendar/callback/`      | None (public)            | Google redirects the browser here after consent - and this one view does the entire rest of the exchange itself, no separate `/complete/` step. Unsigns `state` (`google_oauth.unsign_oauth_state()`, expecting `flow="shared"` - see "Routing two flows through one OAuth app" below) - redirects with `#gcal_error=Invalid Google Calendar connection attempt.` if it doesn't decode or has expired (10 minutes); `#gcal_error=...was cancelled or failed.` if consent was denied (no code). Only then exchanges the code with Google and fetches the connected account's email - redirects with `#gcal_error=This is not the shared Google Calendar account used for appointment sync...` unless that email case-insensitively equals `settings.GOOGLE_CALENDAR_ID`. Only then does it look up the active `User` whose login email matches **and** who has an active platform `Admin` or `Associate` profile, and saves the tokens onto that user's `GoogleCalendarConnection` (ORM-evict any other connection that stale-held the same `google_email`, then revoke those copied grants after commit). Unique-email race: if this user is already connected as that email, treat it as success (the one-time `code` is already spent); else retry persist once; else redirect with an error flag. On success, redirects to `ADMIN_FRONTEND_URL/#gcal_connected=1` - the frontend learns `google_email` afterwards from `GET /google-calendar/`, not from this redirect. Raises a config error (`ImproperlyConfigured`) instead of redirecting if `ADMIN_FRONTEND_URL` isn't set. |
| `DELETE /google-calendar/disconnect/` | Admin or Associate (JWT) | Revokes the token with Google, then flips the signed-in user's own `GoogleCalendarConnection.is_active` to `False` - `google_email`/`google_access_token`/`google_refresh_token`/`google_access_token_expires_at`/`last_synced_at` are all left exactly as they were, as a record of the last connection. Check `is_active` **and** `google_refresh_token` (i.e. `is_connected`) to know if actually still connected, never `google_refresh_token` alone. If the caller is the fixed shared calendar organizer (`google_email == settings.GOOGLE_CALENDAR_ID`), disconnecting kills sync for every center - platform `Admin` may disconnect; an associate must be `is_active` **and** hold `is_admin=True` on at least one active center assignment - 403 otherwise. Reconnecting the same account (via `/connect/` + `/callback/` again) sets `is_active` back to `True` and restores live tokens.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `POST /google-calendar/refresh/`      | Admin or Associate (JWT) | Forces a refresh of the signed-in user's own tokens right now via `google_oauth.refresh_access_token()`, regardless of whether the stored access token has actually expired - unlike the lazy, only-if-expired refresh `get_valid_access_token()` does internally before every Calendar API call. Requires `is_active` and a live `google_refresh_token` (same connected test as status). Saves the new `access_token`/`expires_at` (and `refresh_token`, if Google rotates it) via `update_google_calendar_tokens()`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `GET /google-calendar/`               | Admin or Associate (JWT) | Returns `{"data": {"google_email": "...", "is_connected": true/false}}` for the signed-in user's `GoogleCalendarConnection` - `is_connected` is `connection.is_active` **and** `bool(connection.google_refresh_token)`, not just whether `google_email` is set (see the "last connected as \_\_\_" note above). Soft-off (`is_active=False`) matches `get_fixed_calendar_organizer()` skipping that row. Never exposes the token columns themselves.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

**Why `/connect/` doesn't redirect directly:** the callback (`/callback/`) is a
plain browser navigation triggered by Google - it can't carry our
`Authorization` header. So `/connect/` is a normal JSON endpoint the
frontend calls first; the frontend itself then sends the browser to the
returned `auth_url`.

**Why `/callback/` does the whole exchange itself now, instead of handing
off to a separate `/complete/`.** An earlier version of this flow kept them
separate specifically so failures could come back as a proper JSON `detail`
message from a normal `POST` the frontend calls with `fetch`/`axios`,
rather than being squeezed into a URL-safe error code. That still holds in
spirit - `/callback/` redirects with a full, human-readable message in
`#gcal_error=<message>` (URL-encoded, but otherwise the exact same string a
JSON `detail` field would have carried), so nothing was actually lost by
dropping the second hop. What's gained: one fewer network round trip, one
fewer endpoint to maintain, and the frontend has nothing left to do after
the redirect except show a toast and re-fetch its status query - it never
has to know a `ticket`/`code` exists at all. The one real cost is that a
failure surfaces as a URL fragment instead of an HTTP error status; that's
an acceptable trade here because every failure message is already a fixed,
short, pre-written string (see the endpoint table above) - there's no
per-field validation error shape that would be awkward to flatten into a
URL.

**Identity: how we know which user connected.** For this shared flow,
identity comes from Google itself, never from anything the frontend sends -
there's no user/associate id passed to `/connect/` for this (contrast with
the personal flow below, where `/callback/` has no other way to know whose
connection to save to). After exchanging the code, `/callback/` calls
`fetch_email()` to get the connected account's own (Google-verified) email,
and **first rejects it outright**
unless it case-insensitively equals `settings.GOOGLE_CALENDAR_ID` - the one
configured shared account (redirects with `#gcal_error=This is not the
shared Google Calendar account used for appointment sync. Connect the
configured shared account instead."). This is not a per-user "connect your
own calendar" flow; only the one fixed shared account may ever hold tokens
through this endpoint. Only past that check does it look up the `User`
whose **login** email (`User.email`) matches that same email, requiring
`User.is_active`**and** an active platform`Admin`or`Associate` profile
(`#gcal_error=No active Biopeak admin or staff account uses this Google
account's email..." otherwise) - `GoogleCalendarConnection.google_email`
(the "you're connected as \_\_\_" column) is a separate field that gets set
to whatever email that lookup matched. Whoever actually signs into Google
on the consent screen decides who gets the tokens - not whoever called
`/connect/`, so there's no way for one user to mint a
consent link and have someone else's approval land tokens on the wrong
row. Practical effect: **whoever administers the shared Google account
must also be an active Biopeak Nexus admin or staff login with that same
email address** - if no active admin/associate login email matches
`GOOGLE_CALENDAR_ID`, connecting is impossible until one is created/updated
to match.

**Why `state` here isn't a CSRF nonce.** `/callback/` (for the shared flow)
never reads `request.user`, so there's no session-based action for a CSRF
nonce to guard against being triggered on someone else's behalf, and a
valid `code` can only exist if someone actually completed Google's own
consent screen for our registered `client_id` - Google's own
client-secret-backed exchange (`exchange_code()`) already guarantees that.
This app _does_ use `state` (see "Routing two flows through one OAuth app"
below), primarily to tell the shared and personal connect flows apart, and

- for the personal flow specifically - to carry the initiating user's id
  through Google and back with tamper-proof integrity (since that request has
  no `request.user` of its own). It's still not "was this `code` used within
  N minutes of a `/connect/` call," which isn't a meaningful security
  boundary here.

**Why the redirect never carries the connected email:** URL fragments and
query strings both end up in browser history, but query strings additionally
end up in proxy/CDN logs and the `Referer` header sent to the next page. Even
carried as a fragment, `/callback/`'s final redirect only ever includes one
plain outcome flag - `#gcal_connected=1` or `#gcal_error=<message>` - never
the raw `code`, never the tokens, and never the connected Google email
either way. The frontend gets the email later, from `GET /google-calendar/`
(the status endpoint), once it re-fetches after seeing `#gcal_connected=1` -
not from the redirect itself.

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

One row per `User`. For the _shared_ flow specifically, only the one login
whose email matches `settings.GOOGLE_CALENDAR_ID` will ever have tokens
populated that way - `/callback/` rejects any other Google account for
that flow (see "Identity" above). The _personal_ flow (see "Personal
calendar connect & availability sync" below) deliberately populates this
same table for any staff login that connects their own account, so in
practice this table does hold one row per connected staff member overall -
just not through the shared flow's endpoint.

| Column                           | Type                   | What it stores                                                                                                | Why we need it                                                                                                                                                                                          |
| -------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user`                           | OneToOne `User` (PK)   | The Biopeak login that owns this connection (`Admin` or `Associate`)                                          | Either account type can hold the shared calendar tokens. Distinct from center-admin `AssociateCenterAssignment.is_admin`.                                                                               |
| `google_email`                   | Email (optional)       | The connected Google account's email, e.g. `care@biopeak.health` (should match `settings.GOOGLE_CALENDAR_ID`) | Shown in the UI as "Connected as \_\_\_". Distinct from `user.email` (the login email) - this is the _connected Google_ account, which may differ.                                                      |
| `google_access_token`            | Text (optional)        | An encrypted, short-lived Google access key (expires in about an hour)                                        | Needed to make Google Calendar API calls on the owner's behalf. Encrypted before saving - never stored as plain text.                                                                                   |
| `google_refresh_token`           | Text (optional)        | An encrypted, long-lived Google key that doesn't expire on its own                                            | Used to get a new `google_access_token` automatically once the old one expires, without asking the owner to reconnect. Encrypted before saving.                                                         |
| `google_access_token_expires_at` | Date + time (optional) | When `google_access_token` stops working                                                                      | Lets the code check "has this expired?" and refresh it first if so.                                                                                                                                     |
| `last_synced_at`                 | Date + time (optional) | When `POST /google-calendar/sync/` last _completed successfully_ for this connection                          | Drives the "Last synced \_\_\_" label in Settings; null means never synced (or every attempt so far has failed). Personal-connect-only in practice - the shared organizer account never calls `/sync/`. |
| `watch_channel_id`               | String (optional)      | Our own random id (`uuid.uuid4()`) for the active Google push-notification channel                            | Identifies which channel a `POST /google-calendar/webhook/` call is about; also what we hand back to Google's `channels.stop` on disconnect. Indexed - the webhook looks connections up by this.        |
| `watch_resource_id`              | String (optional)      | Google's own id for the watched calendar resource, returned by `events.watch`                                 | Google requires both `id` (channel id) and `resourceId` together to identify/stop a channel - neither alone is enough.                                                                                  |
| `watch_expires_at`               | Date + time (optional) | When the current channel stops sending notifications                                                          | Google calendar watch channels aren't renewable in place - a new one is created ahead of this and the old one stopped, see "Personal calendar webhook" below.                                           |

All four token/email columns are optional (nullable); `last_synced_at` and
the three `watch_*` columns are too, and none of them are what decides
whether the connection itself is still live (that's `is_active` +
`google_refresh_token`, as above).

Separately, `AssociateAvailabilityBlock` (`appointments/models.py`) carries
a `google_event_id` column (blank for anything created through the regular
manual Blocks API) - see "Personal calendar connect & availability sync"
below for what tags it and why. Disconnecting (`db.deactivate_google_calendar_connection()`,
also used when a refresh token turns out to be revoked/invalid - see "How it
works" step 7 above) never nulls any of the token/email/`last_synced_at`
columns - it only flips `is_active` to `False`, same soft-delete convention
as everywhere else in this codebase. `google_email` and the tokens are
deliberately left in place as a record of the last-connected account (see
"Why `/disconnect/` ..." above for why anything checking "is this user
connected" must test `connection.is_active` **and** `google_refresh_token`

- i.e. `is_connected` - not `google_email` or the presence of a token alone).

**Uniqueness:** `google_email` must be unique, case-insensitively -
`models.UniqueConstraint(Lower("google_email"), ...)`
(`integrations/models.py`), not a plain `unique=True`, since two emails that
only differ by case are still the same Google account; lookups against it
use `__iexact` throughout. Postgres allows any number of `NULL`s under the
constraint either way. Because disconnect leaves `google_email` in place, a
later reconnect by a _different_ user to the same Google account is handled
at connect time instead: `/callback/`'s shared `_persist_connection()`
helper proactively evicts whichever other connection currently holds that
`google_email` - unlike a self-disconnect, this eviction **does** clear the
evicted row's `google_email` too (all four columns), since the new
connection is about to be saved with that same `google_email` value and the
old row must give it up first. Evict copies the stale row's refresh token,
then ORM-clears that row and saves the new connection inside
`transaction.atomic()`. Revoke of those copied grants runs **after** commit
so a rollback cannot leave Google dead while local tokens still look
connected. `InvalidToken` or Google HTTP failure on that post-commit revoke
is logged and ignored (local columns are already cleared). If
`connection.save()` hits the unique-email `IntegrityError`,
`_persist_connection()` re-reads: this user already connected as that email
→ treated as success (OAuth `code` is one-time and already spent); else
retry persist once; still colliding → redirects with an error flag.

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

**`watch_channel_id` / `watch_resource_id` / `watch_expires_at`** on
`GoogleCalendarConnection` back the push-notification
webhook - see "Personal calendar webhook (push notifications)" below.
**Still intentionally left out:** no `sync_token` column - the webhook only
triggers a re-run of the existing full-window `sync_google_events_to_availability_blocks()`,
it doesn't do an incremental `events.list` fetch. That's a possible later
efficiency improvement, not required for correctness (see that section).

## Event sync (book/reschedule/cancel)

Sync is best-effort and **asynchronous**. Book / cancel / reschedule enqueue
WhatsApp + Google Calendar rows on `CommunicationOutbox` via
`schedule_queue_*` (`transaction.on_commit`). The request never calls Google.
**A Google Calendar failure must never block, fail, or roll back an
appointment operation in Biopeak Nexus.**

Worker: `uv run manage.py process_communication_outbox` (wake on insert +
15-minute sweep). `process_google_outbox_message` calls
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
has to go through the normal `/google-calendar/connect/` + `/callback/`
flow - its tokens live on the one `GoogleCalendarConnection` row whose
`google_email` (the connected-Google-account column) matches
`GOOGLE_CALENDAR_ID` (`/callback/` rejects any other Google account
outright for this flow, see "Identity" above). `get_fixed_calendar_organizer()` filters
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

## Personal calendar connect & availability sync

Separate from everything above: lets **any** signed-in Admin or Associate
connect their own personal Google Calendar from Settings and pull its busy
events into Biopeak as `AssociateAvailabilityBlock` rows, so time already
blocked on their real calendar (a lunch break, a recurring standing
appointment, anything added straight into Google rather than into Biopeak)
also blocks that time here - without anyone re-entering it by hand.

**Same table, different rules.** Tokens still live on the caller's own
`GoogleCalendarConnection` row (1:1 `User`) - there's no second table, and
both flows are completed by the same `GoogleCalendarCallbackView.get()`
(see "Routing two flows through one OAuth app" below for how it tells them
apart). Where they differ is _which_ user the tokens save onto and how
that's checked: the shared flow resolves the owning `User` purely by
matching the connected account's email against `settings.GOOGLE_CALENDAR_ID`
then `User.email` (`_complete_shared_connection()`) - the caller of
`/connect/` is never even authenticated, so there's no "caller" to compare
against. The personal flow instead always saves onto whichever user's id
was signed into `state` at `/personal/connect/` time
(`_complete_personal_connection()`, since that request _is_ authenticated -
see "Routing two flows through one OAuth app" below) - but it then requires
the connected Google account's own email to case-insensitively match that
same user's `User.email` (their Biopeak login), rejecting the connection
with `#gcal_error=Connect the same Google account you log into Biopeak
with.` if it doesn't. **This is a deliberate policy, not a security
mechanism** - saving onto `request.user`'s own row already prevents one
user's approval from landing on someone else's row regardless of whose
Google account is connected, so this check adds no new protection against a
hostile actor. It exists purely so "connect your own calendar" stays
literal: an associate whose personal Gmail differs from their Biopeak login
email cannot use this feature to connect it (they'd need a Biopeak login
that uses that same email). It's also rejected outright if the connected
account is `GOOGLE_CALENDAR_ID` itself (redirects with an error flag so a
stray personal-connect click can never steal the shared organizer's tokens

- see "Identity" above for why the eviction logic itself is otherwise
  generic). `GOOGLE_CALENDAR_STAFF_PERMISSION` (`IsAdminUser | IsAssociateUser`)
  gates `/personal/connect/`, unlike the public shared-flow `/connect/`;
  `/callback/` itself stays public either way, since it's Google calling, not
  the frontend.

**Scope.** Both flows request the same `google_oauth.SCOPES`
(`calendar.events` - full read/write, plus `userinfo.email`). The
personal-calendar sync code itself only ever _reads_ (see `availability_sync.py`
below) - it doesn't use the write half of this scope today - but it's
granted upfront anyway, so a future personal-calendar write feature (e.g.
mirroring an associate's own Biopeak appointments onto their personal
calendar) doesn't require everyone who already connected to reconnect and
re-consent just to pick up more scope. `build_auth_url()` no longer takes a
`scopes` override - there is nothing left to differentiate.

**Routing two flows through one OAuth app.** Both flows share the same
Google OAuth client and the same registered redirect URI
(`GOOGLE_REDIRECT_URI`), so `/callback/` can't tell them apart from the URL
alone - and for the personal flow specifically, `/callback/` also has no
`request.user` of its own (it's Google calling, not an authenticated
frontend request) to know _whose_ tokens these are. Both problems are
solved the same way: `build_auth_url()` takes a `state` argument built by
`google_oauth.sign_oauth_state(flow, user_id=None)` - `{"flow": "shared"}`
for `/connect/`, or `{"flow": "personal", "user_id": "<caller's own id>"}`
for `/personal/connect/` (its own `request.user.pk`, from that endpoint's
JWT) - signed with `django.core.signing` (no database row - a stateless,
tamper-proof, 10-minute-expiring blob keyed off `settings.SECRET_KEY`).
Google echoes `state` back verbatim on redirect; `/callback/` unsigns it
(`google_oauth.unsign_oauth_state()`) to recover both which flow this is
and, for the personal flow, which user to save onto - a `state` tampered
with in transit (e.g. someone editing `user_id` to try to attach their
Google account to a different Biopeak login) is cryptographically
guaranteed to fail signature verification, not merely "the frontend
happened to build the request correctly." `state` here is still purely a
routing/identity-carrying concern, not a CSRF nonce - see "Why `state` here
isn't a CSRF nonce" above. One-time-use isn't separately enforced on `code`
by this app - Google's own token endpoint already rejects a `code` that's
exchanged twice, which is where that guarantee actually needs to live.

**Endpoints:**

| Endpoint                                                                | Auth                     | What it does                                                                                                                                                                                                                                      |
| ----------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /google-calendar/personal/connect/`                               | Admin or Associate (JWT) | Returns `{"data": {"auth_url": "..."}}` with `state` signed as `{"flow": "personal", "user_id": <caller's id>}`. Same scope as the shared flow (see "Scope" above). `/callback/` (shared by both flows) does the rest - see "How it works" above. |
| `POST /google-calendar/sync/`                                           | Admin or Associate (JWT) | Runs the sync described below for the caller. 400s if not connected.                                                                                                                                                                              |
| `GET /google-calendar/`                                                 | Admin or Associate (JWT) | Same status endpoint as the shared flow (it's per-user already) - now also returns `last_synced_at`.                                                                                                                                              |
| `DELETE /google-calendar/disconnect/`, `POST /google-calendar/refresh/` | Admin or Associate (JWT) | Unchanged, already per-signed-in-user - reused as-is for a personal connection.                                                                                                                                                                   |

**What counts as "busy."** `integrations/google_calendar/availability_sync.py`
calls `calendar_api.list_events()` (`events.list` with `singleEvents=false`,
so a recurring event stays a single master item carrying its `recurrence`
RRULE instead of being expanded into per-occurrence copies) over a rolling
`SYNC_WINDOW_DAYS` (30) window starting now. An event is skipped (not
imported) if it's cancelled, marked free (`transparency: "transparent"` -
Google Calendar's own "Free" vs "Busy" toggle), or declined by the caller
themselves (`attendees[].self.responseStatus == "declined"`). An all-day
event (`date` instead of `dateTime` on `start`/`end` - e.g. a leave/
out-of-office entry) or an event with `eventType: "outOfOffice"` is imported
as an **`AssociateLeave`** instead of a block (see "Leave" below), unless it
carries a `recurrence` (Biopeak leave has no recurrence, so a recurring
all-day event stays a recurring block).

**One-off vs recurring, using the same create path the manual Blocks API
uses - minus the overlap check.** `build_spec_from_event()` builds a
plain dict, then `_create_blocks_for_spec()` calls the same
`create_associate_availability_block()` (`appointments/serializers/__init__.py`)
the `POST .../availability/associates/<id>/blocks/` endpoint uses, but
deliberately skips `assert_associate_block_no_overlap()`
(`appointments/utils/overlap.py`) - Biopeak allows overlapping availability
blocks, so an imported block is free to coincide with any other block
(manual or Google-imported) on the same center/associate. It still runs
`apply_availability_exception_hooks()` (source_type=`ASSOCIATE_BLOCK`) so
appointments that now conflict get flagged the same way. A non-recurring
Google event (no `recurrence`) becomes a one-off block
(`is_recurring=false`, `start_datetime`/`end_datetime`). A recurring event
only imports if `parse_supported_rrule()` can map its RRULE onto the recurring
block payload (`days_of_week`, `recurring_start_time`/`recurring_end_time`,
`effective_from`, `effective_until`):

| Google repeat option                      | RRULE                               | Biopeak recurring block                            |
| ----------------------------------------- | ----------------------------------- | -------------------------------------------------- |
| Daily                                     | `FREQ=DAILY`                        | `days_of_week` = all 7 (`"0"`..`"6"`, Mon=`"0"`)   |
| Weekly on Thursday                        | `FREQ=WEEKLY;BYDAY=TH`              | `days_of_week=["3"]`                               |
| Every weekday                             | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR`  | `days_of_week=["0","1","2","3","4"]`               |
| Custom, every 1 week, chosen days         | `FREQ=WEEKLY;BYDAY=SU,MO,TU,TH,SA`  | matching `days_of_week`                            |
| Ends "On date"                            | `UNTIL=...` added                   | `effective_until` = last date an occurrence starts |
| Ends "After N occurrences"                | `COUNT=N`                           | **skipped** (no equivalent)                        |
| Every N > 1 days/weeks, monthly, annually | `INTERVAL>1`, `FREQ=MONTHLY/YEARLY` | **skipped**                                        |

Skipped means never approximated - the event is simply not imported.
`EXDATE` (deleted single occurrences) is ignored, so the block still covers
that day (over-blocks rather than under-blocks).

**Leave.** An all-day or Out-of-office event (non-recurring) becomes one
`AssociateLeave` with `scope=all_centers`, `center=null`, e.g. all-day
17-18 Sep -> `start_datetime` `2026-09-17T00:00:00+05:30`, `end_datetime`
`2026-09-18T23:59:59+05:30`, `reason` = event title (fallback
`"Leave (Google Calendar)"`). `AssociateLeave.google_event_id` (blank =
created manually) drives the same reconcile as blocks: unchanged -> skip,
edited -> deactivate + recreate, gone from Google -> soft-deactivate. An
event that flips between leave and block (e.g. ticking "All day") is
deactivated on its old side and created on the new one. No overlap check;
exception hooks run once per active center.

**Every active center, not just one.** `AssociateAvailabilityBlock.center`
is a required FK - there's no "all centers" block type (unlike
`AssociateLeave.scope=ALL_CENTERS`). An associate can be actively assigned
to more than one center at once, and a Google Calendar busy event means
they're unavailable everywhere, not just at one location - so `sync_...()`
loops every active `AssociateCenterAssignment` and creates one copy of the
block per center. A caller with no active `Associate` profile, or an active
profile but zero active center assignments, gets a no-op response
(`{"synced": false, "reason": "..."}`), not an error - there's nothing to
import into.

**Re-syncing is idempotent and reconciling, not purely additive.** Every
imported block row is tagged `google_event_id` (blank for anything
manually created through the regular Blocks API - never ambiguous which
rows came from where). Each `POST /sync/` re-diffs the caller's fetched
events against their previously-imported rows, per Google event id:

- **Unchanged** (same center set, same time/day/reason as last sync) - left
  alone entirely, no write, no re-run of the exception scan.
- **New or edited** - any previously-imported rows for that event id are
  made inactive (`is_active=false`, never hard-deleted), their open exceptions
  are resolved, and fresh rows are created for every center and repeat day,
  all in one short transaction per event. Exception scans run after it
  commits. There's no overlap check here (see above). If two syncs race on the
  same event, a partial unique constraint (active rows only) stops the second
  write and that event is skipped.
- **Gone** - its previously-imported `origin=google` rows are made inactive
  (soft-off, same convention as every other soft-delete in this codebase) and
  their open exceptions resolved. This only fires when the event is actually
  gone from Google's side (deleted, marked free, or declined by the
  associate) - not merely absent from one fetch. A block created directly
  in Biopeak (`google_event_id=""`) is excluded from this check entirely
  and is never touched by the sync, and a one-off imported block whose
  `end_datetime` has already passed is also excluded - Google's `timeMin`
  filters by event end time, so an already-ended event naturally drops out
  of the fetch whether or not anyone deleted it, and treating that as
  "gone" would misreport a normal, harmless expiry as a removal. Recurring
  blocks don't need this carve-out: Google's `timeMin` already drops a
  recurring series once its `UNTIL` has passed, and a still-running one
  always keeps showing up in every fetch - so its absence means it was
  deleted/freed/declined in Google, or its series simply ended.
- **Present but unreadable** - an event still on Google's calendar that we
  can't import (unsupported `RRULE`: `INTERVAL>1`, `COUNT`, monthly, bad
  bounds) is _not_ "gone". Its already-imported rows are left exactly as they
  are (nothing created, nothing removed). Only an event that is missing from
  the fetch, or that Google marks cancelled / free / declined / Biopeak-outbound,
  is soft-offed.
- **Google rows are read-only in the API.** `AssociateAvailabilityBlockSerializer`
  and `AssociateLeaveSerializer` expose read-only `origin` and `google_event_id`,
  and a PATCH on an `origin=google` row returns 400 (edit it in Google
  Calendar). Otherwise the next sync would just recreate it.

`GoogleCalendarConnection.last_synced_at` is set only after a sync actually
completes successfully - not on every click, and not on a failed one.

## Personal calendar outbound (Biopeak → Google)

Reverse of inbound sync: when staff create/update/soft-off an associate
**block** (one-off or recurring) or **leave** in Biopeak, the API enqueues a
`CommunicationOutbox` row (`channel=google_calendar`, event
`associate_block_sync` / `associate_leave_sync`) via
`schedule_queue_associate_block_sync` /
`schedule_queue_associate_leave_sync` (`transaction.on_commit`). The same
outbox worker dispatches to
`integrations/google_calendar/personal_outbound.py`, which upserts/deletes on
the associate's **personal** calendar through
`send_google_calendar_outbound_event` (not the shared organizer).

**Loop fence (two layers).** `AssociateAvailabilityBlock.origin` /
`AssociateLeave.origin` is `manual` (API) or `google` (inbound sync). Only
`manual` rows enqueue or write back. Inbound reconcile and `_remove_rows` only
touch `origin=google` rows (so MANUAL rows that carry a `google_event_id` after
outbound are never replaced or removed by import). Outbound insert/patch also
stamps private `extendedProperties.private.biopeakOutbound=1`; inbound
`build_spec_from_event` skips those events so Biopeak-written busy never
re-imports even if the webhook races ahead of persisting `google_event_id`.

Appointment events carry the shared key
`extendedProperties.shared.isAppointment=1` (`upsert_google_event` in
`google_sync.py`, checked via `event_is_appointment` in `calendar_api.py`).
Google copies `shared` properties onto every attendee's copy, and the
associate's personal calendar (which inbound sync reads) holds the attendee
copy. `biopeakOutbound` is `private` because personal outbound events live on
the associate's own calendar.

Inbound sync also skips any event whose `organizer.email` equals
`GOOGLE_CALENDAR_ID`, since every appointment is organized by the shared
calendar. Both checks sit in `should_skip_inbound` (split into
`_google_marks_free` and `_is_biopeak_event`). A skipped event takes the
"gone" path, so rows imported from it before (e.g. an old invite that became a
duplicate) are removed.

**Shared organizer is never synced inbound.** `sync_google_events_to_availability_blocks`
returns `synced: false` for the `GOOGLE_CALENDAR_ID` connection, and
`ensure_watch_channel_active` never opens a watch channel for it. This covers
every caller (manual sync, admin sync of an associate, webhook, watch renewal,
first sync after connect). Both sync views return 400 for it.

**Recurring.** A multi-day create shares one `series_id`; one outbox target +
one Google master with `RRULE:FREQ=WEEKLY;BYDAY=...`. Soft-off / edit of any
row in the series rebuilds from all still-active siblings.

**Not connected.** Outbox still enqueued; worker marks `SKIPPED` with
`"Personal Google Calendar not connected"` (no Google HTTP).

**Schema.** `CommunicationOutbox.appointment` is nullable; exactly one of
`appointment` / `associate_availability_block` / `associate_leave` /
`availability_series_id` (DB check). Partial unique on open PENDING/FAILED
google rows per series/block/leave target. User runs migrations for new columns
(`origin`, `series_id`, outbox FKs/uniques, leave `google_event_id` max_length)
— agent does not write them.

## Personal calendar webhook (push notifications)

Everything above ("What counts as busy", re-syncing) still describes the
actual diffing logic - `sync_google_events_to_availability_blocks()` is
unchanged. This section is only about _what triggers_ that function: instead
of relying solely on someone clicking `POST /sync/`, Google can call us the
moment a personal calendar actually changes, so a lunch break or leave added
directly in someone's own Google Calendar shows up as a Biopeak block within
moments - not whenever that person (or a scheduled job) next happens to hit
`/sync/`.

**Registering a channel.** Right after a personal connect succeeds
(`GoogleCalendarCallbackView.get()`, `flow == FLOW_PERSONAL`), and again on
every sync call (self `POST /google-calendar/sync/` and the admin per-associate sync) as a self-heal,
`ensure_watch_channel_active()` (`integrations/google_calendar/webhook_channel.py`)
checks whether the connection's channel is missing or expiring within
`RENEWAL_THRESHOLD` (1 day) and, if so, calls `events.watch` on Google's
Calendar API (`calendar_api.watch_events()`) with a fresh random channel id
(`uuid.uuid4()`), asking Google to POST to `https://api.biopeak.com/google-calendar/webhook/`
whenever that calendar changes. Google's response (`resourceId`, and the
`expiration` it actually granted - which can be shorter than the
`WATCH_TTL` requested) is persisted onto the four `watch_*` columns (see
"Database columns" above). **This is entirely best-effort** - a failure here
is logged and swallowed (`GOOGLE_SYNC_ERRORS`), never surfaced as a
connect/sync failure, since the connection is still fully usable through
manual `/sync/` even with no channel registered at all.

**The shared organizer never gets a channel.** Nothing reads busy time back
from `settings.GOOGLE_CALENDAR_ID`'s own calendar (it's the one-way
Biopeak→Google direction described above `Personal calendar connect &
availability sync`), so `personal_connections_needing_watch_renewal()`
explicitly excludes whichever connection holds that email.

**Renewal.** Google Calendar watch channels aren't renewable in place - a
new channel has to be created and the old one stopped. `uv run manage.py
process_google_calendar_channel_expiry_renewal` (same style as
`process_communication_outbox`) should run on a daily schedule; it calls
`ensure_watch_channel_active()` for every personal connection whose channel
is missing (no channel or no expiry) or expires within a day. A renewal creates the new channel first and only then stops the old one, so a failed start keeps the old channel. Even without that command running, a
channel gets renewed lazily the next time that user hits `POST /sync/` -
the scheduled command just means it happens without anyone needing to.

**Receiving a notification.** `POST /google-calendar/webhook/`
(`GoogleCalendarWebhookView`, public - Google is calling, not an
authenticated frontend request) reads three headers Google sends, no body:
`X-Goog-Channel-ID`, `X-Goog-Resource-ID`, `X-Goog-Resource-State`. It looks
up an active `GoogleCalendarConnection` by channel id + resource id
(`find_connection_for_watch_channel()`) - an unrecognized channel is logged
and ignored, not rejected with an error status. `channel_id` is a random
`uuid.uuid4()` we mint ourselves and never expose outside the
Google<->server exchange, so this id+resource-id match is the verification.
`X-Goog-Resource-State: sync` is
Google's one-time handshake right when the channel is first created, not a
real change - it's a no-op. Any other state (`exists`, the only other value
Calendar's `events.watch` sends) means "something on this calendar changed,
go look" - it re-runs the exact same
`sync_google_events_to_availability_blocks()` that `POST /sync/` calls
manually, for that connection's own user. **This endpoint always answers
200**, even when the channel is unrecognized or the sync itself fails
(`GOOGLE_SYNC_ERRORS`, logged) - Google retries a non-2xx response with
backoff and can eventually stop a channel that keeps failing, which would be
worse than silently no-op'ing one bad notification.

**Notifications carry no event data.** Unlike, say, a WhatsApp status
webhook, Google's Calendar push notification is deliberately a bare "go
check" signal - it never says _what_ changed. That's why the webhook calls
the same full-window sync function `/sync/` uses rather than trying to patch
one event: there's nothing in the notification to patch with. A `sync_token`-based
incremental fetch (see "Database columns" above) would still call
`events.list`, just with a narrower diff to compute - a possible later
optimization, not a correctness requirement today.

**Disconnecting stops the channel.** `DELETE /google-calendar/disconnect/`
calls `stop_watch_channel()` before revoking the OAuth grant, which calls
Google's `channels.stop` and clears all four `watch_*` columns. Same
best-effort philosophy as everywhere else here: if Google can't be reached,
the columns are still cleared locally (so a stale channel id can never
falsely match a future notification) and disconnect proceeds regardless -
an unstopped channel simply expires on Google's side on its own.

**Endpoint:**

| Endpoint                         | Auth          | What it does                                                                                                                                                                  |
| -------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /google-calendar/webhook/` | None (public) | Google's push-notification callback. Verified via channel id + resource id match, not JWT. Always responds 200. See above for what it does with each `X-Goog-Resource-State`. |

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
