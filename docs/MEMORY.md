# Biopeak Nexus — Project Memory

Non-obvious decisions, agent prefs, traps. No code dumps. No CLAUDE.md / CODING_RULES.md clones. Specs in `docs/`.

---

## User Preferences

- Code explain → clickable `[file.py:42](path/to/file.py#L42)` every mention.
- Never revert/alter code user manually edited. User change-back = final.
- Never `select_for_update()`. Ordinary ORM. No row locks.
- Never write migration files. Never `makemigrations`. User owns migrations.
- UUID detail URLs: `<uuid:pk>/`.
- No fn return/output type annotations unless asked.
- Prefer `timezone.localtime()` for persisted timestamps.
- No `transaction.atomic()` inside helpers unless asked.
- ePRDs: concrete request/response JSON + integration logic. No TypeScript / base-type / interface decls.
- Prefer explicit `BaseModelSerializer` + `Meta.model` + declared fields. No `to_representation()` delegate.
- Keep related-object fields nested. Don't flatten.
- Don't repeat explicit `read_only=True` fields in `Meta.read_only_fields`.
- Never put derived service-document module-category props/display on model. Serializers compute code+label from `ServiceResult.document_type`.
- API add/change → update `bruno/` same change. Source of truth = `bruno/`. Envs: `bruno/environments/{Development,Production}.bru`. No folder vars (folder > env → blank tokens).
- **Bruno auth (2026-09-12):** 401 `"Authorization header must contain two space-delimited values"` = empty Bearer. Empty runtime `access_token` masks env. Never `auth: bearer` + `{{access_token}}`. Collection `bruno/collection.bru` pre-request sets `Authorization` from env → collection → runtime (skip empty; skip `/webhooks/` + Google callback). Requests/folders `auth: inherit`. Pre-consultation folder overwrites w/ `customer_access_token`. Login Phone Direct: `bru.deleteVar('access_token')` before set. Empty optional query → `~param:`.
- **Bruno Find Slots (2026-09-15):** `POST .../appointments/slots/` preferred keys `room_id`, `equipment_id`, `care_team_id`, `doctor_id`, `specialty_id`. `health_coach_id` → 400. Empty interpolated UUIDs strip in pre-request. `care_team_id` XOR `doctor_id`/`specialty_id`. Room with ≥1 bookable equipment → `equipment_id` required. Env: `slot_date`, `doctor_id`, `specialty_id`.
- List filter query = `active=0|1`. Model/body/response stays `is_active`. Never `is_active` as query name.
- Center resource lists (associates + v2 room-types / equipment-types / rooms / equipment / services): omit `active` → both. `active=0|1` still filters. Availability lists default-active-only.
- Don't send empty UUID query params. Disable w/ `~room_type_id: {{room_type_id}}`. Junk UUID on rooms list → 400 `"Invalid room_type_id."`
- **Rooms `type_active`:** `GET /centers/<uuid>/v2/rooms/?type_active=0|1`. `1` = `room_type_ref` set + `RoomType.is_active`. `0` = type null or inactive. Omit/junk = no filter. Independent of room `active=`.
- **Equipment `type_active` + `room_allotted`:** `GET /centers/<uuid>/v2/equipments/?type_active=0|1&room_allotted=0|1`. Independent AND. `type_active` same as rooms. `room_allotted=1` = `room` set + `Room.is_active`. `0` = room null or inactive. Omit/junk = no that filter. Independent of equipment `active=`.
- **Success envelope (mandatory):** `{detail, data}` via `send_response` / `response_format` / `Base*APIView`. `data` = object, list, or omit. Never top-level array. Never nest `{detail, data}` inside `data`. Never raw `Response(payload)`. List-creates: `data` = array; client uses `data[0].id`. No `success` key (pre-consult only). Custom list-create: override `post()` + `send_response(..., status=201)`. Do **not** `send_response` inside `create()` on `BaseListCreateAPIView` → nested envelope.

---

## 2026-09-11 — Multi-role associates, multi room types, preference-only booking

- Migrations: `associates.0020` add `AssociateCenterAssignmentRole`, copy `role_id` rows, drop `AssociateCenterAssignment.role`; `services.0008` add `CenterServiceRoomTypeRequirement`, copy `required_room_type_id` rows, drop `CenterServiceAssignment.required_room_type`; `appointments.0019` `AppointmentAssociate` UniqueConstraint `(appointment, associate)`. Schema bootstrap removed from tests. 0020/0008 applied w/o copy → rollback those apps then remigrate.
- Associate API hard-break: write `role_ids[]` only; response `role_ids` + `roles[]`; no singular `role`/`role_id`. Admin still no care roles. RBAC `AssociateFeaturePermission` = OR across multi-roles.
- `CustomerAssociateSerializer` exposes `roles`/`role_ids` from `current_center_assignment` through-links.
- Care team member still one `role_id` per row; role ∈ associate's live roles at center.
- Slots/book/reschedule: FE sends staff+room+equipment IDs. Find Slots nests under `preferred`; book/reschedule flatten top-level. No `associates[]` pin. No auto-fill from service role/room pools. `health_coach_id` → 400 use `specialty_id`. `specialty_id` = service-mapped person; `doctor_id` may be extra. `doctor_id` stamps unique live `"doctor"`-in-name hat. `specialty_id` stamps live non-doctor hat ∩ service active role reqs (many specialty hats OK). Zero overlap / no service role reqs → 400. Two+ mapped → stamp one (stable `pk`). Same person both IDs → 400. Dup associate on apt → 400 (+ DB unique).
- Room types on assignment: OR eligibility. Write via `RoomType.filter_active(center=...)`. Center service V2 write/read `required_room_type_ids[]` (not singular).

## 2026-09-15 — Flattened book/reschedule; chosen equipment

- Book/reschedule body: `start`, `end`, `customer_profile_id`, `service_id`, `modality`, `room_id`, `equipment_id`, `doctor_id`, `specialty_id`, `care_team_id`, `notes`. No nested `preferred`, no `associates[]` pin. Hats from doctor/specialty/care_team IDs.
- Find Slots keeps `preferred` nest; add `equipment_id`. Room w/ ≥1 bookable equipment → required; else omit. Bookable = active + `equipment_type` set + type active + `room` = chosen room.
- Room type must be active; mapped to service room-type reqs when those exist (OR). No preferred-room override of unmapped types.
- `specialty_id` hat = live non-doctor role ∩ active service role reqs (many hats OK). No unique-hat 400. No `role_id` in body. Service w/ 0 role reqs + `specialty_id` → 400. `doctor_id` still unique `"doctor"`-in-name hat, not service-mapped.
- Find Slots each slot: nested `care_team` / `doctor` / `specialty` (`role` on specialty) / `room` / `equipment` `{id, name}` — omit key if not in preferred. No `associates[]`. No bare `*_id`. Book still flattened IDs from those `id`s.

## 2026-10-06 — Customer booking window (tomorrow…today+7)

- Customer Find Slots / book / reschedule: local date must be `today+1` … `today+7` inclusive (rolling). Staff unchanged (today + open future).
- Helper `ensure_customer_booking_date(slot_date, center, …)` in `appointments/serializers/booking.py` — bounds via `center_local_date` (lives in `appointments/utils/calendar.py`; today = settings.TIME_ZONE until Center has TZ). Message: `"Date must be between tomorrow and 7 days from today."`
- Reschedule uses same window vs request day (not original apt day).

## 2026-10-07 — Therapy book vs package expiry (issue #111)

- Product: **block** booking/slots/reschedule/complete when appointment local date `> program.expires_at` (null expiry = open-ended). Not “valid today → any future date”.
- `ensure_program_covers_appointment_date` + `resolve_bookable_therapy_program_service(..., appointment_date=)` in `appointments/utils/redemption.py`. Message: `"This package expires on {D Mon YYYY}. Please choose a date on or before it."` (f-string; no `.format`).
- Customer slots: optional `program_service_id`; omit → ORM block only if every matching active therapy line for customer+service expires before `date`.
- Reschedule (customer + staff therapy-linked): same expiry vs new `start`. Complete gate only in lifecycle `validate` + `force_complete_appointment` (before status flip) — not inside `complete_appointment_redemption`.

## 2026-10-06 — App download QR redirect

- Public `GET /app/` (`integrations.communications.app_download.AppDownloadRedirectView`). Wire: `core/api/urls.py` → `integrations.communications.urls`.
- Shipped QR = `https://biopeak.app/scan` (frozen). Must DNS/CDN 302/rewrite → Nexus `/app/` (optional `src`). This BE has no `/scan` route.
- UA: Android → Play; iOS (`iphone`/`ipad`/`ipod` or `macintosh`+`mobile` for iPadOS) → App Store (`https://apps.apple.com/app/biopeak/id6759485756`, no `/in/`); else HTML `assets/templates/app_download/Biopeak_App_Download.html`.
- Query `platform=android|ios` overrides UA (chooser store badges re-hit `/app/` so store pick is tracked). Junk/other ignored. QR URL never gains `platform`.
- `AppDownloadClick.entry`: `ua` (mobile UA → store), `chooser` (fallback HTML), `platform_query` (badge `?platform=`). Derived server-side.
- Best-effort insert first (`platform`, `entry`, `destination_url`, UA, IP, `src`/`campaign`, referer) — `DatabaseError` logged, redirect/HTML still returned. Skip insert when UA matches `APP_DOWNLOAD_BOT_USER_AGENT_PATTERN`.
- IP: `get_request_ip_address` uses **last** `X-Forwarded-For` hop (ALB-appended) + `ipaddress` validate; invalid → null. `AppDownloadThrottle.get_ident` uses same helper.
- Throttle: scope `app_download` `60/min` via LocMem (per-process; no Redis). Soft limit only — tighten at ALB/WAF if needed.
- Admin: `AppDownloadClick` add/change denied (append-only list/delete).
- Chooser render uses `request._request` (Django `HttpRequest`). Store hrefs = `/app/?platform=…&src=…` track URLs, not raw store URLs.
- No agent migration — user `makemigrations integrations` (`entry` + `(entry, created_at)` index; fold into `0011` if not applied yet).

## 2026-10-06 — QR redeem + open appointment

- QR `SINGLE` with open apt: `try_complete_open_appointment_for_single_redeem` — complete+burn; CAS miss + already `completed`+`REDEEM` → idempotent success; never fall through to classic `redeem_program_service` after open apt observed (cancelled → 400, no classic burn).
- Open apt may be at any center; body `center_id` only needs service available there (QR redeemable cross-center by design).
- `increment_therapy_sessions_used` no-ops when finite and would exceed remaining; `force_complete_appointment` invalidates ops cache.
- Partial unique `uniq_open_appt_per_ps`: dedupe open appts per `program_service` before migrate if leftovers.

## 2026-09-24 — Unified Find Slots + customer self-serve

- Single `POST /centers/<id>/appointments/slots/`: staff **must** send `preferred`; customer **must not** (auto-assign via `find_appointment_slots_v2`). Empty/`{}` preferred = missing for staff, forbidden if key present for customer.
- Dropped `/v2/slots/` (unused). Engines stay separate.
- `GET /appointments/customer-appointments/<customer_profile_id>/` — customer only; owned profile (all centers). Optional `therapy_service_program=0|1`: `1` = `program_service` set; `0` = null; omit/junk = all. Sort: in_progress → confirmed → checked_in → completed → cancelled → no_show, then start ascending.
- Book / cancel / reschedule — staff **or** customer (own profiles; cancel/reschedule other → 404).
- Center resolve for customers requires active `CustomerCenterAssignment`.

## 2026-09-22 — Find Slots auto-assign engine (least-busy)

- Engine `find_appointment_slots_v2` (invoked from unified slots when customer, no preferred).
- Pools from service maps: active role requirements → eligible associates (multi-role via `role_links`); `in_person` rooms from active room-type requirements (OR). Equipment = bookable units on chosen room (no service↔equipment-type map).
- Per slot window: pick least-busy free resource. Busy metric = `len` busy appointment intervals that day. Ties: associate `created_at`+`pk`; room/equipment `code`+`pk`.
- ≤1 doctor-named role on the service. Multiple specialty (non-doctor) roles OK. Slot `specialty` = one object when 1 specialty, array when 2+. `in_person` needs ≥1 room-type req. No care-team auto-pick.
- Book/reschedule: `specialty_id` = UUID | UUID[]. Each id stamps a distinct service-mapped non-doctor hat. Preferred-path slots stay single `specialty_id` UUID.

## 2026-09-15 — GoogleCalendarConnection

- Tokens off `Associate` onto `GoogleCalendarConnection` (1:1 `User` PK). Admin or associate may own shared calendar. `/complete/` match `User.email` + active Admin/Associate. Status/disconnect/refresh = `IsAdminUser | IsAssociateUser`. Success `user_id` not `associate_id`.
- User writes migration: create table, copy live Associate google cols, drop Associate google cols + `uniq_associate_google_email`. No `makemigrations` from agent. `integrations.0003` copies then `associates.0021` depends on it.
- Evict stale `google_email`: ORM-evict + save **inside** `/complete/` `atomic()` first; revoke copied stale refresh grants **after** commit (`InvalidToken`/HTTP fail still fine — local already cleared). Status/refresh connected = `is_active` + `google_refresh_token`. Disconnect still revokes if tokens exist on soft-off row.
- `/complete/` unique-email `IntegrityError`: this user already connected as that email → 200 (code spent). Else retry persist once. Still colliding → 400. Never tell reconnect just cos one-time code used.
- `get_valid_access_token()` `invalid_grant`: re-read row; retry once if `google_refresh_token` changed; only `deactivate_google_calendar_connection()` when token we sent still stored (see 2026-09-17 rename/behavior change below).

## 2026-09-17 — Personal Google Calendar connect + availability sync

- Separate from shared-organizer; same table (`GoogleCalendarConnection`, 1:1 `User`) + `last_synced_at`. `/personal/connect/`+`/personal/complete/` (JWT `IsAdminUser|IsAssociateUser`) → any staff connect own Google — no `User.email` match required; tokens save onto `request.user` row. 400 if connected account == `GOOGLE_CALENDAR_ID`. Read-only scope (`calendar.events.readonly`) — never writes personal calendar. Shared `/connect/`+`/complete/`+`/callback/` thread `state` (`shared`/`personal`, `google_oauth.OAUTH_STATE_*`) via `build_auth_url()`→Google→`/callback/` so FE knows which `/complete/` — routing hint only, not CSRF.
- `AssociateAvailabilityBlock` gained `google_event_id` (blank = manual). `POST /google-calendar/sync/` (`integrations/google_calendar/availability_sync.py`) pulls caller Google events (`events.list`, `singleEvents=false` — RRULE master, not expanded) rolling **30-day** (`SYNC_WINDOW_DAYS`), reuses `create_associate_availability_block()` — never reimpl. **No overlap check**. Skips: cancelled, `transparency=transparent`, all-day (no `dateTime`), self-declined.
- Recurring import: plain never-ending weekly RRULE only (`FREQ=WEEKLY`, no `INTERVAL`>1, no `UNTIL`/`COUNT`, `BYDAY` weekday tokens) — else skip, never approx. One-off Google → one-off block.
- Associate active at N centers → block at **every** active center (vs primary-only). Real-world unavail not center-scoped though `AssociateAvailabilityBlock.center` required FK (no `AssociateLeave`-style `ALL_CENTERS` for blocks).
- Re-sync reconciles (vs additive-only): per Google event id vs previously-imported active rows — unchanged (same center-set+time/day/reason) → skip; new/edited → replace+create inside **one short `atomic()` per event**; gone from Google → removed. (Overlap-conflict skipping removed; see 2026-09-21.)
- Each created block runs `apply_availability_exception_hooks(source_type=ASSOCIATE_BLOCK)` parity w/ manual.
- `last_synced_at` only after sync **succeeds**.
- Model adds: `integrations.GoogleCalendarConnection.last_synced_at`, `appointments.AssociateAvailabilityBlock.google_event_id`. **No agent migration** — user `makemigrations`/`migrate`.
- FE (`Biopeak-Nexus-Admin-FE`): no Google Calendar UI yet — first build in `SettingsPage`, card/`createMutation`+`createQuery`/Zustand-auth patterns from scratch.
- **Follow-up:** `/callback/` no longer forwards raw `code`/`state` — signs `{code, state}` opaque ticket (`google_oauth.sign_oauth_redirect()`/`resolve_oauth_ticket()`, `django.core.signing`, 10-min expiry, no DB/cache — stateless off `SECRET_KEY`) → redirect `#t=<ticket>` only. `/complete/` + `/personal/complete/` take `{"ticket": ...}` not `{"code": ...}`; `resolve_oauth_ticket()` checks `state` matches endpoint (shared vs personal) — no cross-flow replay. Bruno: `google_oauth_code` → `google_oauth_ticket`.
- **Bug caught:** FE OAuth-callback hook only in `ProtectedLayout`, but `ADMIN_FRONTEND_URL` → `/` renders `<Login/>` — authed user hits `Login.tsx:125-128` `<Navigate to={resolveLoginRedirect(...)} replace/>` before `ProtectedLayout` → drop hash. Fix: capture `#t=...` sync at `App.tsx` module scope (`captureGoogleCalendarOAuthTicket()`, same spot as `hydrateFromToken()`), stash `sessionStorage`, strip hash. `ProtectedLayout` hook consumes+clears sessionStorage once auth confirmed.
- **Follow-up — personal scope read/write:** grant write upfront. `PERSONAL_SCOPES` (`calendar.events.readonly`) removed; personal connect uses `google_oauth.SCOPES` (`calendar.events`) same as shared — `build_auth_url()` dropped unused `scopes` override. Sync (`availability_sync.py`) still read-only. Future write-back → no reconnect for old read-only grant holders.
- **Follow-up — merge `/callback/` + `/complete/`:** `GoogleCalendarCompleteView`/`GoogleCalendarPersonalCompleteView` + `/complete/`/`/personal/complete/` deleted — `GoogleCalendarCallbackView.get()` (`AllowAny`) does exchange+email+flow+user+save then redirect. `sign_oauth_redirect()`/`unsign_oauth_redirect()` → `sign_oauth_state()`/`unsign_oauth_state()` — `state` carries `{"flow": "shared"|"personal", "user_id": ...}`, signed at connect time, echoed by Google. Only way `/callback/` knows Biopeak user for personal (no JWT on Google redirect). Shared still resolves by email; both sign `state` so tampered flow/user_id rejected.
  - **Follow-up — personal email must match Biopeak login:** `_complete_personal_connection()` `if google_email.lower() != user.email.lower(): return "Connect the same Google account you log into Biopeak with.", None` after `GOOGLE_CALENDAR_ID` check. Product policy not security (tokens already only on `request.user` row). Tradeoff: staff Gmail ≠ Biopeak login blocked.
  - **Follow-up, 2026-09-17 — supersedes lines above on gone/overlap:** (1) "Gone": one-off `google_event_id` deactivation candidate only if `end_datetime > time_min` (recurring always candidates — never-ending `FREQ=WEEKLY` always in window). Else past one-offs miscounted "removed". Biopeak-created (`google_event_id=""`) already `.exclude(google_event_id="")`. (2) `assert_associate_block_no_overlap()` off sync path — overlapping blocks allowed. Per-event savepoint + `skipped_conflicts`/`DRFValidationError` catch removed; `create_associate_availability_block()` unconditional. `"skipped_conflicts"` dropped from return. Manual create still overlap-checked.
  - Refactor: Complete views → `_persist_connection()`, `_complete_shared_connection()`, `_complete_personal_connection()`.
  - `/callback/` redirect: `#gcal_connected=1` or `#gcal_error=<message>` only — never ticket/tokens/email. FE gets `google_email` from `GET /google-calendar/`.
  - FE: `capture-oauth-ticket.ts` → `capture-oauth-result.ts` (`captureGoogleCalendarOAuthResult`/`consumeGoogleCalendarOAuthResult`) — `{status: 'connected'} | {status: 'error', message}`. Hook: toast + `queryClient.invalidateQueries(googleCalendarKeys.status)` only. `useCompleteGoogleCalendarConnect` + `googleCalendarApi.complete()` deleted.
  - Bruno: `Complete.bru`/`PersonalComplete.bru` deleted; Connect/PersonalConnect/Callback docs rewritten; `google_oauth_ticket` → `google_oauth_code`/`google_oauth_state`.

---

## 2026-09-18 — Google Calendar push-notification webhook

- Real-time trigger for `sync_google_events_to_availability_blocks()` (personal only — shared organizer never watched). Prev: manual `POST /sync/` only. New: `POST /google-calendar/webhook/` (public, channel id + resource id verify — see `docs/google-calendar-integration.md`).
- **Blocked on migration agent can't run:** `GoogleCalendarConnection` gained `watch_channel_id`/`watch_resource_id`/`watch_channel_token`/`watch_expires_at`. `makemigrations --check --dry-run` → one `integrations` migration needed — not generated. `integrations/tests/test_google_calendar_webhook.py` → `UndefinedColumn` until `uv run manage.py makemigrations integrations && uv run manage.py migrate`.
- Renewal cmd `process_google_calendar_channel_expiry_renewal` (was `renew_google_calendar_watch_channels`) — daily like `process_communication_outbox`. Also self-heal on every `POST /sync/` via `ensure_watch_channel_active()`.
- Watch channels not renewable in place — `ensure_watch_channel_active()` start new then stop old (best-effort). (Superseded 2026-09-21: used to stop first; failed start → no channel.)
- Webhook = bare "changed, look" signal → full-window sync, not incremental `events.list`. No `sync_token` (deferred efficiency).
- Webhook always 200 — even unknown channel / failed sync (`GOOGLE_SYNC_ERRORS`, logged). Non-2xx → Google retry → channel may stop.
- Bruno: `google_calendar/Webhook.bru` (`auth: none`); `collection.bru` JWT-skip also `/google-calendar/webhook`.
- **Follow-up — `watch_channel_token` removed (supersedes above):** channel id = server `uuid.uuid4()`; `find_connection_for_watch_channel()` on channel+resource id enough. Removed field (migration `0006_remove_googlecalendarconnection_watch_channel_token`), `channel_token_is_valid()`, Google `token`, header check. Debug `print()`/`logger.info()` left (user testing).

## 2026-09-21 — Personal Google Calendar outbound (Biopeak → Google)

- Manual associate block / recurring series / leave create+update+soft-off enqueue `CommunicationOutbox` (`channel=google_calendar`, event `associate_block_sync` / `associate_leave_sync`). Worker desired-state via `personal_outbound.sync_*` → `send_google_calendar_outbound_event` (personal tokens only).
- Loop fence: (1) `AvailabilityOrigin` on block+leave (`manual`|`google`) — inbound reconcile / `_deactivate` only `origin=google`; enqueue + outbound skip non-manual. (2) Outbound insert/patch stamps private `extendedProperties.private.biopeakOutbound=1`; inbound `build_spec_from_event` skips those. Recurring create mints shared `series_id` (one Google RRULE). Outbox: nullable `appointment` + exactly-one target + partial unique on open PENDING/FAILED per series/block/leave target.
- Not connected → outbox SKIPPED `"Personal Google Calendar not connected"`. No agent migrations — user `makemigrations` appointments+integrations then migrate.

---

## 2026-09-20 — Google sync: Google repeat options → Biopeak payloads

- `availability_sync.py` maps Google recurrence → Biopeak recurring-block: `FREQ=DAILY` → all 7 days; `FREQ=WEEKLY` (every 1) + `BYDAY` → those days; `UNTIL` → `effective_until` (last occurrence start date, UTC→local). Support only payload-matched: `COUNT`, `INTERVAL`>1, monthly, yearly **skipped**. `EXDATE` ignored (over-blocks).
- All-day (non-recurring) or `eventType=outOfOffice` → `AssociateLeave` (`scope=all_centers`, `center=null`, all-day end = 23:59:59 not `time.max`). Recurring all-day stays recurring block. Leave reconciles per `google_event_id` like blocks; hooks per active center.
- Model add: `AssociateLeave.google_event_id`. **No agent migration** — user `makemigrations appointments`/`migrate` (`UndefinedColumn` on leave until then).
- **Tests (2026-09-20):** `integrations/tests/test_google_calendar_availability_sync.py` (48 tests, `Test` prefix). `manage.py test` w/ no/app label breaks (`'tests' module incorrectly imported`); run: `uv run manage.py test integrations.tests.test_google_calendar_availability_sync`. Pre-existing fail `appointments.tests.test_associate_google_calendar` (`..._cannot_view_another_associates_status`, `..._cannot_sync_via_admin_only_endpoint`, 400 not 403) on clean HEAD too — fixed 2026-09-29 (renamed).
- **Live gotcha:** watch channel live → Google edits trigger webhook seconds later → manual `POST /sync/` often `0/0/0`. Check DB state, not counts.

---

## 2026-09-12 — Center associate list role filter

- `GET /centers/<uuid>/associates/?role=0|1` uses `Exists` on `AssociateCenterAssignmentRole`. Never `role_links__` JOIN — N active roles → N duplicate assignments.

## 2026-09-12 — Care teams `members_live`

- `GET /centers/<uuid>/care-teams/?members_live=0|1`. `1` = every member live at center w/ mapped role active. `0` = ≥1 broken (inactive user/assignment/unmapped role link/inactive `AssociateRole`). Omit/junk = no filter. Independent of team `active=`. `Exists` on members, not JOIN. Same live rules as booking `members_with_live_center_role`. Team always ≥2 members (write + `members_count>=2`); filter no empty special-case. `1` ≠ bookable-team picker — booking still expands leftover live members.

---

## Non-obvious decisions

Pointers: appointments+availability → [`docs/appointments-frontend-api.md`](appointments-frontend-api.md). Google Calendar → [`docs/google-calendar-integration.md`](google-calendar-integration.md). Result fetch → [`docs/result-fetch-flow.md`](result-fetch-flow.md).

**API / tenancy**

- Customer associate list: `X-Center-ID` present → exclusive center filter; `center_id` query only if header absent. Role join vs each returned customer-assignment center; keep nested roles; no multi-center fan-out.
- **Never** `FilteredRelation` + `prefetch_related` on that alias → Django `ValueError` 500. Prefetch `associate__center_assignments` + `active_role_links_prefetch`; resolve via `assignment_for_center(associate, center_id)`.
- `POST .../link-associates/`: profile missing → 404; dedupe `add`/`remove` IDs before `bulk_create` (dup IDs → Postgres ON CONFLICT 500).
- `Associate.centers_count` = all `AssociateCenterAssignment` rows (any active). Assignment mutations refresh via subquery; center delete bulk-updates before cascade.
- Admin `GET`/`POST /associates/`: max-three center preview, no assignment flags. Create needs non-empty `add_centers`; each `is_admin` and/or `is_care_staff`; dup center UUID = last wins. Create `centers_count` may be stale — FE refetch.
- Hours/closures write: `/centers/<uuid>/availability/operating-hours/` GET/PATCH bulk upsert; `/closures/` GET/POST + PATCH soft reopen. `CenterClosure.type`=`holiday`|`manual` + `reason`. Closures GET `.order_by("-date")` only. Availability URL `<uuid:center_id>` so resource `pk` no collide. Center calendar default `granularity=week`.
- Unassigned admin (no associate profile, or zero active assignments) may hit any center. Associate w/ zero active assignments denied — last-assignment offboard revokes, no escalate.

**Programs / composites / results**

- `CompositeTemplate.code` = required unique user-entered SKU; no sequence UID.
- `ProgramService` line shared: keep `sessions_count`/`sessions_used`/`sessions_cancelled`; `sessions_count=0` = unlimited. Therapy runtime + `RedemptionHistory` → `TherapyProgramService`. Cancel/redemption only if `Program.program_type` is `THERAPY`. `wellness_*` = API aliases.
- Composite add-ons: keep repeated `add_services`; no pricing change; no inherit template prerequisites. Authoritative list: `profiles/<profile_uuid>/programs/composite-program-services/`.
- Composite prerequisites: singleton `CompositeServicePrerequisite` on `CompositeTemplateService`; empty M2M OK; default `require_any`. Spec: [`docs/composite-service-prerequisites-frontend-prd.md`](composite-service-prerequisites-frontend-prd.md).
- Program UID: `P`-prefix ≥4-digit sequence on active therapy+composite create; API `uid` read-only; nullable; no DB unique. `backfill_program_uids` **not run yet**.
- `ServiceResult` belongs to `ProgramService`. Module-category on serializer, not model. Unmapped → `unknown`. Invalid `module_category` query → no rows.
- Counters persist via ORM subquery (include inactive/cancelled); API reads never annotate. Repair: `recompute_service_document_counts`.
- ProgramService cancel: active flag + audit only; result/doc rows unchanged. Therapy cancel needs `X-Center-ID`. Legacy last-service writes parent cancel metadata w/o deactivating parent/subtype.
- Global service → empty `GET /services/<uuid>/centers/`. Spec: [`docs/service-centers-products-frontend-eprd.md`](service-centers-products-frontend-eprd.md).

**Assessments / fetch (2026-09-08/10)**

- `ResultRequest` parent of 1+ `ServiceResult`. Provider via `ResultRequest.product.provider`. Layout: `integrations/<provider>/{sdk,tasks,utils/results}.py`. BugSpeaks = reference. Unknown provider → `None`; unknown product → no-op. Fetch/refetch start `ResultRequestThread`. Refetch reuses request, deletes `ServiceResult`+docs, re-queues. Cancel: `status`+`updated_at` only. Reject completed/already-cancelled. FE does **not** poll.
- Strand NutriDNA + Genomic Health Insights: persist any PDF/VCF/JSON. All present → `completed`; ≥1 missing → `partially_fetched` + `failure_detail`; never `failed` w/o `ServiceResult`. Partial may cancel (keep results) or destructive refetch.
- EVO 360: `client_id`/`client_secret`/`center_id` + `profile_data.email`. One-way PDF only if provider status `found`; else `failed` (no poll). Store `found` in `ServiceResult.data`; don't persist temp PDF URL.
- `ProgramService.fetch_count` = all result requests; `fetch_results_count`/`fetch_documents_count` via `result_mode=fetch`; `fetch_pending_count` excludes completed/failed/cancelled (partial still pending). Hooks refresh 4 together; `recompute_service_document_counts` repairs.

**Leads / onboarding / inventory**

- Onboarding completion only `CustomerProfile.is_onboarding_completed` (not Lead). Both `is_onboarding_sent` default `False`. Admin/associate may PATCH `is_onboarding_completed` on `PATCH /profiles/{id}/` (`CenterCustomerProfileDetailSerializer`); center home list serializer still read-only. Pre-consult complete also sets it. `is_invited` independent. Ready: lead `sent=True` and (no profile or profile incomplete).
- Leads writes `/leads/v2/` (POST create+shell, PATCH update+shell sync). v1 GET/POST/PATCH → 400; v1 DELETE still `/leads/{id}/`. `/auth/login-phone-direct/` = User lookup only, no shell.
- Emergency contact fields dropped from `CustomerProfile` + pre-consult baseline.
- Test kit: app `test_kit_inventory`. Global APIs, no `X-Center-ID`. One active kit/`CustomerProfile`. Eligible = completed pre-consult + no active kit. POST `/assign` `assigned_to` = non-empty profile UUID array; one txn; any fail → none; response `detail` only. `Product.is_assignable` default `False`. QC acks `qc_ack_packaging` / `qc_ack_all_components` write-gate on `Item`.
- Room/equip codes globally unique: `{EQ|RM}-{center.code}-{seq}`. Old `EQ-0005` rows keep format. Seq names stay `equipments_{center_id}` / `rooms_{center_id}`.
- `Service.name` unique catalog-wide, case-insensitive. `Room.name` / `Equipment.name` unique per center, case-insensitive. Same row may keep name. Inactive still occupy name. Existing dups block migrate.

**Diagnostics (Orange Labs)**

- App `diagnostics_orders`. National `CatalogItem` (`test_id` int unique). No city prices / category / fasting / pincode ranges.
- Create: `diagnostic_tests` = int array; Orange splits by `is_custom_package` — `False` → `tests:[{test_id:str}]`, `True` → `packages:[{package_id:str}]`. Local lines all `DiagnosticOrderLine.test_id`. Unique `(order_customer, test_id)`. Token never in FE.
- Auth: `IsAdminUser | IsAssociateUser` (no feature gate; `X-Center-ID` optional by design).
- Webhook `POST /webhooks/orange-labs/`: HMAC `X-OH-Signature` (raw body, SHA256 hex); idempotency `X-OH-Event-Id`; lookup `payload.request.city_request_id` (fallback `payload.order.city_request_id`); status = top-level `event`.
- Eligible customers: active + onboarding completed + active center assignment + no open (non-terminal) order. No program / pre-consult join.
- Migration `0005` first apply **wipes** diagnostics orders + catalog (irreversible; empty = no-op). Re-seed via `POST /add-test-package/`.

**Pre-consult**

- Envelope: `success` top-level only; never in `data`. `pre_consultation_response()` strips stray `success`.
- Baseline v2 PUT requires `height` (cm) + `weight` (kg); persists `CustomerProfile.height_cm` / `weight_kg`. GET returns them (null until set). No unit fields. v1 baseline unchanged.

---

## Appointments / availability traps

Canonical contract: [`docs/appointments-frontend-api.md`](appointments-frontend-api.md).

- Book lands `confirmed`. Cancel/reschedule from `confirmed` or `checked_in`; reschedule lands `confirmed`. `in_progress` not reversible (ack-only exceptions). No-show from `confirmed` only.
- Never `SomeView.as_view()(request)` from another DRF view → re-wrap `Request` → `AssertionError` 500. Dispatch via view instance handler (`dispatch_to_view`).
- Customer overlap GiST **global** (any center) on busy exclusive range. Python busy map: customer, no center filter. Concurrent book: GiST also on room / equipment / associate. Loser `IntegrityError` → `"Slot no longer available."` No `select_for_update()`.
- Slot/book IDs: `customer_profile_id` / `service_id` vs this center's active assignment. Miss/inactive/other-center → 400 `"Invalid customer profile for this center."` / `"Invalid service for this center."` (no existence oracle).
- Find Slots `date` < `timezone.localdate()` (`Asia/Kolkata`) → 400 `"Date cannot be in the past."` (not empty `slots`). Today still OK; elapsed starts today still omitted in `find_appointment_slots`. Direct book/reschedule `start` < `timezone.now()` → same 400.
- Idempotent book: look up `Idempotency-Key` **before** `resolve_booking_combo`. Same key+payload → 200 `"Appointment retrieved."` without re-checking the slot. Same key+different payload → 409.
- Slots return **one combo** per start/end. Slot body nested `care_team`/`doctor`/`specialty`/`room`/`equipment` (omit absent). Book/reschedule flatten `doctor_id`/`specialty_id`/`care_team_id`/`room_id`/`equipment_id` (no pin `associates[]`). `care_team_id` XOR doctor/specialty. `doctor_id` outside service roles → extra, not 400. `specialty_id` must map a live non-doctor hat to this service’s role reqs. in_person always needs room else 400. Room must have active `room_type_ref`; if assignment has room-type reqs, type ∈ that set (OR). Equipment: FE pick; room with ≥1 bookable (active + type active + on that room) → `equipment_id` required; 0 bookable → omit; no first-unit auto-pick. Virtual: no room/equipment. `end` == `start` + assignment duration.
- `Appointment.notes` writable on book/reschedule; omit/`null` on reschedule keeps existing; `""` clears. Not passed raw to Google — wrapped via `build_appointment_*_notes()`.
- List `?search=`: customer name/email/phone, apt `code`, service name. `search` w/o `start` = all dates, newest first. Hard-cap 500. `associate_id`/`role_id` match `associates[]`; together = **OR**.
- Exceptions `status` query `open`|`resolved`; junk → 400.
- Care team: name unique per center case-insensitive. Member write rejects inactive `AssociateRole` (`400` `"Role is inactive."`). Expand live assignment does **not** 400 when team misses a service role — leftover roles searched. Empty live members + `care_team_id` → 400 `"Care team has no live members at this center."`.
- Availability: PATCH `is_active=false`; no DELETE. Recurring POST `days_of_week` `"0"`…`"6"` → 1 row/day; 201 `{detail, data}` `data` = list. Assoc one-off = datetimes; room/equip one-off + downtime = `date`+`start_time`+`end_time` (`settings.TIME_ZONE`). `scope=all_centers` leave stores `center=null`. Leave wins vs associate block. Downtime wins vs room/equip block.
- Roster ⊆ center hours: write 400 if before open / after close / closed day / missing hours. Hours PATCH 400 if shrink/close would leave active roster outside. Codes: `before_opening`, `after_closing`, `center_closed`, `center_hours_missing`, `roster_on_closed_day`. Inclusive edges. Existing out-of-range rows stay until next save. Roster POST/PATCH enqueues async `associate_roster` scan; response top-level `exception_scan`.
- Care-team calendar base = intersect live members' (center ∩ roster). Team blocks subtract from member associate calendars + slots + ops capacity. Overlap only vs other active blocks on **same** team. `ExceptionSourceType.CARE_TEAM_BLOCK` matches `Appointment.care_team` only (not solo member apts). `PATCH is_active=false` also soft-deactivates that team's active blocks **and resolves** those open `care_team_block` exceptions; reactivate does not revive. One-off ExclusionConstraint; recurring Python-only.
- Exception scans: PATCH of window fields (`start_datetime`/`end_datetime`/`date`/`start_time`/`end_time`/`day_of_week`/`effective_from`/`effective_until`/recurring times) retriggers detection. Scan also **closes** open exceptions that no longer overlap. Create / reactivate / deactivate still hooked.
- Operations dashboards: junk `start`/`end` → 400 `"Invalid start|end date. Use YYYY-MM-DD."`; junk `granularity` → 400 `"Invalid granularity. Use day, week, or month."`; end before start → 400. Booked minutes/hours/counts/utilization/bottleneck dependents = busy statuses only (`confirmed`/`checked_in`/`in_progress`).

---

## Communications / Google Calendar traps

Canonical: [`docs/google-calendar-integration.md`](google-calendar-integration.md).

- WhatsApp **not** in `products.Provider`. Env secrets only (token, phone id, etc.). Template **names** in `integrations.utils.constants.WHATSAPP_TEMPLATE_BY_EVENT` — not env. Meta lifecycle names: `appointment_confirmed_template` / `appointment_cancelled_template` / `appointment_rescheduled_template`; reminder/no-show stay `therapy_session_*`. Façade `integrations/communications/` → WhatsApp SDK + Google desired-state.
- Book/cancel/reschedule **enqueue only** via `transaction.on_commit` (`schedule_queue_*`). Outbox fail cannot roll back apt write. Missing WA env → skip that channel; apt still saves.
- Reminder: sweep `enqueue_appointment_reminders` (confirmed, start within next 1h) → WA outbox only, **no** SQS wake; same `sweep_jobs.sh` then runs `process_communication_outbox`. Once any reminder outbox row exists (any status incl. SKIPPED), never enqueue again. Cap 50/sweep (= outbox drain limit). Virtual address/Meet: confirm/reschedule `clinic_address` + reminder/no-show `{{4}}` = center address (in_person) or Meet link / fallback “Check your calendar invite…” (virtual). No-show: lifecycle `schedule_queue_appointment_no_show` → WA only + wake.
- Outbox `CommunicationOutbox` (`channel=whatsapp|google_calendar`). Worker `process_communication_outbox` (SQS wake + 15 min sweep). Claim via conditional `update` (no `select_for_update`). Stale WhatsApp `SENDING` → **SKIPPED**; stale Google `SENDING` → **FAILED** (retry). HTTP WhatsApp success w/o parsable `wamid` still ACCEPTED; max 2 attempts then SKIPPED.
- **WA vs Meet (Option A, 2026-09-30):** Book/cancel/reschedule enqueue **GC then WA**. Confirm/reschedule virtual WA defers only while Meet blank **and** same-apt Google still open (`PENDING`/`FAILED` retryable/`SENDING`). Meet already set (reschedule) → no wait. Cancel / reminder / no-show never defer for Meet. In-person never waits. Rebuild `template_parameters` at WA send from live apt. After apt GC `ACCEPTED`/`SKIPPED`, wake if pending WA remains. Reminder/no-show stay WA-only.
- Unique `(appointment, channel, event_type)` for terminal events: confirmed, cancelled, reminder, no_show — while status in pending/sending/accepted/sent/delivered/read/**failed** (blocks dup while worker retries). Reminder sweep also anti-joins **any** existing reminder row (incl. SKIPPED). Google coalesces one open row per appointment. Webhook `get_or_create` on `event_key`; `IntegrityError` → dup. Webhook `GET|POST /webhooks/whatsapp/`.
- Ops: SQS wake + EventBridge `rate(15 minutes)` `assets/scripts/sweep_jobs.sh` (reminders → outbox → exception scans → Google watch renewal). Env `*_COMMUNICATION_OUTBOX_WAKE_QUEUE_URL`. **Not** in `deploy-aws.yml`.
- Google: one fixed shared organizer (`GOOGLE_CALENDAR_ID`). Tokens on `GoogleCalendarConnection` (1:1 `User`, admin or associate). Resolve via `google_email__iexact` + connection/user active + live admin/associate profile + live `google_refresh_token` (not email alone — disconnect keeps `google_email`).
- Sync best-effort async. Never Google HTTP on request path. `GOOGLE_SYNC_ERRORS` = `(requests.RequestException, ValueError, InvalidToken, ImproperlyConfigured)` — exclude `KeyError`/`TypeError` (our bugs must crash).
- Event id = appointment UUID hex. Book title `"Appointment Confirmed"`; reschedule `"Appointment Rescheduled"`. Cancel does **not** clear `google_event_id`/`google_meet_link`. Leave virtual → clear Meet (`clear_meet_link=True`). Insert/patch success then `appointment.save` `DatabaseError` → log+swallow; do **not** delete Google event.
- `/connect/` + `/complete/` public (`AllowAny`); never read `request.user`. `/complete/` rejects unless Google email equals `GOOGLE_CALENDAR_ID`; then match `User.email` + active `Admin` or `Associate` (user active). Tokens on `GoogleCalendarConnection`. `google_email` uniqueness case-insensitive (`Lower`). Stale email on other connection → ORM-evict + save inside `atomic()`, then revoke copied stale grants after commit (`InvalidToken`/HTTP fail still clear local). Unique race: reuse if this user already connected as that email; else retry persist once; else 400 (do not burn the user on a spent code if we already saved). Success `user_id` (not `associate_id`).
- Disconnect/status/refresh: `IsAdminUser | IsAssociateUser`. **(2026-09-17 change)** Disconnect/revoke no longer nulls any column — `db.deactivate_google_calendar_connection()` only flips `is_active=False`, leaving `google_email`/tokens/`last_synced_at` in place as a record of the last connection. "Connected" (`is_connected`) = `is_active` **and** `google_refresh_token` truthy — never either alone. Soft-off row: status/refresh read as disconnected; disconnect view itself now gates on `google_calendar_connection_is_connected()` (not a raw `google_refresh_token` check) so it no-ops on an already-inactive row instead of re-revoking. Reconnect (`persist_google_calendar_connection`) flips `is_active` back to `True` and overwrites tokens. Shared-organizer disconnect: platform `Admin` OK; associate needs `is_active` + `is_admin` on ≥1 active center assignment (403 else). `InvalidToken` on decrypt → deactivate, no 500.
- Deactivate (was "clear tokens") only on Google `invalid_grant` (`google_oauth.is_invalid_grant_error`) when the refresh token we sent is still the stored one. Concurrent worker rotated the grant → re-read + retry once, do not deactivate. Other 400 (`invalid_client`/`invalid_request`) must not deactivate. `/complete/` fail-fast if client secret or encryption key missing **before** `exchange_code` (code is one-time). `revoke_token()` no-op only on 400; other non-OK raise. Disconnect lets revoke `RequestException` → 503 (don't mark disconnected while Google grant live).
- Virtual Google description = Meet-join line, no clinic address. Other modality = `Center.full_address` (computed, not a column). Dead HTML email path deleted; Google invite = only customer-facing notify.

---

## Conventions (not in CODING_RULES.md)

- ORM lookups in serializers/utils: `filter(...).first()`. No `.get()`; handle missing explicitly.
- Serializer add/remove: write-only `{id}` lists; pop w/ `[]` fallback; one query + set diff; save → remove before add → refresh counts → return. Spec: [`docs/m2m-serializer-pattern.md`](m2m-serializer-pattern.md).
- Views: `*ViewMeta` + `filter_kwargs = {}` on `BaseGenericAPIView`. No standalone queryset utils. No `http_method_names`. Serializers never import ViewMeta querysets. `utils/db.py` = mutations only. Representation uses prefetched `to_attr`.
- Serializer `create()`/`update()` own persistence. Views pass context to `serializer.save(...)`; must not capture return, assign `serializer.instance`, or reload for write-response. Route getters take no id args; resolve `self.kwargs["pk"]` via `get_object_or_404`. Shared `*ViewMeta` only if `pk` same resource type. Create needing nested prefetch: reload via ViewMeta queryset → `serializer.instance`.

---

## Tooling

**django-debug-toolbar v7:** `include("debug_toolbar.urls")` OK. `CompressedManifestStaticFilesStorage` needs `collectstatic` or toolbar.js null `dataset`. Fix: `uv run manage.py collectstatic` after upgrade.

## 2026-09-21 — Google availability sync review fixes

- Inbound sync (`availability_sync.py`): one short `atomic()` **per Google event**; exception hooks after commit; concurrent dup `IntegrityError` → log+skip, not raise.
- **Edited/gone = soft-off + recreate (reviewer 2026-09-21; update-in-place tried+reverted).** Edited → old `origin=GOOGLE` `is_active=False`, fresh rows every center/day, one short `atomic()`; then `trigger_exception_resolution` + `invalidate_operations_cache` on deactivated pks, then hooks on new. Gone → soft-off + same resolution. Inactive accumulate OK. Unique constraints cover active only. MANUAL untouched.
- New partial `UniqueConstraint`s (active + `origin=google` + non-blank `google_event_id`) on block `(associate, center, google_event_id, day_of_week)` (`nulls_distinct=False`) and leave `(associate, google_event_id)`. **No agent migration** — user `makemigrations appointments`. Dup active Google rows → migration fail; delete dupes first.
- Watch renewal also covers connected personal rows w/ null/empty channel or null `watch_expires_at`. `ensure_watch_channel_active_or_log()` = best-effort wrapper for self sync, admin/peer sync, connect.
- `send_google_calendar_outbound_event` + appointment `upsert_google_event` share `upsert_event_with_fallback()` (patch → stale → insert → conflict → patch).
- **Not done (needs infra):** webhook still syncs inline before 200. Async needs inbound-sync queue (model + migration + worker); outbox is appointment/block-keyed. Follow-up.

## 2026-09-29 — Appointment invites vs. personal Google sync

- Apt flag = `extendedProperties.shared.isAppointment` (attendee copies see shared). `biopeakOutbound` = private (personal calendar owns those).
- Inbound also skip `organizer.email == GOOGLE_CALENDAR_ID`.
- Shared-organizer gate inside `sync_google_events_to_availability_blocks` + `ensure_watch_channel_active` (all callers). Both sync views → 400.
- Inbound skip = `should_skip_inbound` = `_google_marks_free` (cancelled/transparent/self-declined) OR `_is_biopeak_event` (outbound/isAppointment/organizer=`GOOGLE_CALENDAR_ID`). Both → "gone" path → old imported rows removed. Never move Biopeak skips → "unreadable" (keeps rows).
- **Open (PR #94):** `ensure_watch_channel_active` *would* stop leftover shared-organizer channel, but sync views 400 *before* call; renewal queryset also `exclude`s `GOOGLE_CALENDAR_ID`. Leftover channel → Google TTL (webhook sync noops). Fix: stop in shared-organizer 400 branch (both sync views) and/or renew shared rows still w/ `watch_channel_id`.
- Associate center gcal status/sync: `IsAdminUser | IsAssociateUser`; associate needs matching `X-Center-ID` (else 400). Tests: `test_associate_can_*_with_matching_center_header` / `test_associate_without_center_header_is_rejected` (old 403 names gone).

## 2026-09-30 — View tests

- `development.py` forces the debug toolbar on (`SHOW_TOOLBAR_CALLBACK: lambda request: True`), so `APIClient`/`Client` requests through the middleware stack 500 with `Missing staticfiles manifest entry for 'debug_toolbar/...'`. Test views with `APIRequestFactory` + `View.as_view()(request, **kwargs)` (a real `Authorization: Bearer` header from `get_tokens_for_user()` still exercises JWT auth). Paginated list payload is `response.data["data"]` (a list), not `["data"]["results"]`.

## 2026-09-30 — Appointment ↔ therapy redemption

- `Appointment.program_service` nullable FK → `programs.ProgramService`. Partial unique: one open apt (`confirmed`/`checked_in`/`in_progress`) per `program_service`.
- `RedemptionHistory.appointment` OneToOne nullable. New types: `scheduled`, `cancelled` (keep `cancel` = entitlement cancel).
- Book: **customer required** `program_service_id` (omit/null → 400); **admin/associate forbidden** (present → 400, walk-in only). Customer when set → history `scheduled`, no `sessions_used` bump. Complete (lifecycle or QR) → `redeem` + `sessions_used`+1. Cancel/no-show → `cancelled`, no burn.
- Reschedule: **customer required** `program_service_id` matching existing apt FK (omit → same required 400; mismatch → `"program_service_id does not match this appointment."`). No re-resolve / no open-apt self-collision. Staff forbidden. FK never rewritten. Customer UI never lists staff walk-ins (`program_service` null) — mismatch-on-null is dead API path, not a product flow.
- QR `redeem_code` (on `TherapyProgramService`): open apt on that line + single redeem → force-complete apt; else classic redeem. Redeem-all blocked while open apt exists.
- Therapy services list nests `active_appointment` only for open statuses; completed/cancelled/no_show → `null`.
- Appointment list/detail nest `center` `{id, code, name}` via `MinimumCenterSerializer` (same as `active_appointment.center`).
- Helpers: `appointments/utils/redemption.py`. **No agent migration** — user `makemigrations` appointments + programs.

## 2026-10-08 — Wearables Phase 1 backend

- Additive Django/PostgreSQL `wearables` app; do not reuse the ROOK test app's FastAPI, MongoDB, or parallel authentication layer.
- Option 1 API contract only: `/devices/*`, `/health/*`, and `/webhooks/rook/*`. Do not add `/wearable/*` aliases.
- Biopeak `CustomerProfile` is the tenant/member boundary. Each profile has one stable ROOK user ID and history survives provider disconnect.
- ROOK signed data webhooks are primary; durable jobs normalize documents and compute backend-owned daily summaries, trends, confidence, completeness, and six fixed domain cards. API recovery pull is fallback only.
- Never convert missing health data to zero or interpolate gaps. Frontend receives backend-computed states/actions/graph data and must not calculate trends.
- Environment flags plus the existing profile feature model gate rollout. Production defaults wearable/timeline APIs off.
- **No agent migration** — user runs `makemigrations wearables customers` after reviewing models and retention requirements.
