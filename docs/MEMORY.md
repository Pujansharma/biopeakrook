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

- Migrations: `associates.0020` add `AssociateCenterAssignmentRole`, copy `role_id` rows, then drop `AssociateCenterAssignment.role`; `services.0008` add `CenterServiceRoomTypeRequirement`, copy `required_room_type_id` rows, then drop `CenterServiceAssignment.required_room_type`; `appointments.0019` `AppointmentAssociate` UniqueConstraint `(appointment, associate)`. Schema bootstrap removed from tests. If 0020/0008 already applied without copy, rollback those apps then remigrate.
- Associate API hard-break: write `role_ids[]` only; response `role_ids` + `roles[]`; no singular `role`/`role_id`. Admin still cannot get care roles. RBAC `AssociateFeaturePermission` = OR across multi-roles.
- `CustomerAssociateSerializer` exposes `roles`/`role_ids` from `current_center_assignment` through-links.
- Care team member still one `role_id` per row; role must be ∈ associate's live roles at center.
- Slots/book/reschedule: FE sends staff+room+equipment IDs. Find Slots nests under `preferred`; book/reschedule flatten same keys at top level. No `associates[]` pin. No leftover auto-fill from service role/room pools. `health_coach_id` → 400 use `specialty_id`. `specialty_id` = service-mapped person; `doctor_id` may be extra (not on service). `doctor_id` stamps unique live `"doctor"`-in-name hat. `specialty_id` stamps a live non-doctor hat ∩ this service’s active role requirements (person may hold many specialty hats). Zero overlap / no service role reqs → 400. Two+ mapped → stamp one (stable `pk`). Same person both IDs → 400. Dup associate on apt → 400 (+ DB unique).
- Room types on assignment: OR eligibility. Write via `RoomType.filter_active(center=...)`. Center service V2 write/read `required_room_type_ids[]` (not singular).

## 2026-09-15 — Flattened book/reschedule; chosen equipment

- Book/reschedule body: `start`, `end`, `customer_profile_id`, `service_id`, `modality`, `room_id`, `equipment_id`, `doctor_id`, `specialty_id`, `care_team_id`, `notes`. No nested `preferred`, no `associates[]` pin. Hats stamped from doctor/specialty/care_team IDs.
- Find Slots keeps `preferred` nest; add `equipment_id`. Room with ≥1 bookable equipment → required; else omit. Bookable = active + `equipment_type` set + type active + `room` = chosen room.
- Room type must be active; mapped to service room-type reqs when those exist (OR). No preferred-room override of unmapped types.
- `specialty_id` hat = live non-doctor role ∩ active service role requirements (many hats OK). No unique-hat 400. No `role_id` in body. Service with 0 role reqs + `specialty_id` → 400. `doctor_id` still unique `"doctor"`-in-name hat, not service-mapped.
- Find Slots each slot: nested `care_team` / `doctor` / `specialty` (`role` on specialty) / `room` / `equipment` `{id, name}` — omit key if not in preferred. No `associates[]`. No bare `*_id`. Book still flattened IDs from those `id`s.

## 2026-09-15 — GoogleCalendarConnection

- Tokens off `Associate` onto `GoogleCalendarConnection` (1:1 `User` PK). Admin or associate may own shared calendar. `/complete/` match `User.email` + active Admin/Associate. Status/disconnect/refresh = `IsAdminUser | IsAssociateUser`. Success `user_id` not `associate_id`.
- User writes migration: create table, copy live Associate google cols, drop Associate google cols + `uniq_associate_google_email`. No `makemigrations` from agent. `integrations.0003` copies then `associates.0021` depends on it.
- Evict stale `google_email`: ORM-evict + save **inside** `/complete/` `atomic()` first; revoke copied stale refresh grants **after** commit (`InvalidToken`/HTTP fail still fine — local already cleared). Status/refresh connected = `is_active` + `google_refresh_token`. Disconnect still revokes if tokens exist on a soft-off row.
- `/complete/` unique-email `IntegrityError`: if this user already connected as that email → 200 (code already spent). Else retry persist once. Still colliding → 400. Never tell them to reconnect just because the one-time code was used.
- `get_valid_access_token()` `invalid_grant`: re-read row; retry once if `google_refresh_token` changed; only `deactivate_google_calendar_connection()` when the token we sent is still stored (see 2026-09-17 rename/behavior change below).

## 2026-09-17 — Personal Google Calendar connect + availability sync

- New, separate feature from the shared-organizer flow above, same table (`GoogleCalendarConnection`, 1:1 `User`) + new `last_synced_at` col. `/personal/connect/`+`/personal/complete/` (both JWT `IsAdminUser|IsAssociateUser`) let _any_ staff login connect _their own_ Google account — no `User.email` match required, tokens always save onto `request.user`'s own row. 400 if the connected account == `GOOGLE_CALENDAR_ID` (protects the shared organizer row from a stray personal-connect click). Read-only scope (`calendar.events.readonly`) — this flow never writes to a personal calendar. Shared flow's `/connect/`+`/complete/`+`/callback/` now also thread a `state` query param (`shared`/`personal`, `google_oauth.OAUTH_STATE_*`) through `build_auth_url()`→Google→`/callback/` so FE knows which `/complete/` to call — routing hint only, not CSRF (unchanged reasoning, see doc).
- `AssociateAvailabilityBlock` gained `google_event_id` (blank = manually created, matches this repo's "no source field yet" gap noted by Explore research — now filled). `POST /google-calendar/sync/` (`integrations/google_calendar/availability_sync.py`) pulls caller's own Google events (`events.list`, `singleEvents=false` — keeps recurring events as one RRULE-carrying master item, not expanded instances) for a rolling 90-day window, reuses `create_associate_availability_block()` + `assert_associate_block_no_overlap()` (the exact functions the manual Blocks API uses) — never reimplemented. Skips: cancelled, `transparency=transparent` (Google's own Free toggle), all-day (no `dateTime`), self-declined events.
- Recurring import only supports a plain never-ending weekly RRULE (`FREQ=WEEKLY`, no `INTERVAL`>1, no `UNTIL`/`COUNT`, `BYDAY` all weekday tokens) — Biopeak recurring blocks have no end date so anything else is skipped, never approximated. One-off Google event → one-off block.
- Associate active at N centers → block created at **every** active center (user picked this over primary-only): real-world unavailability isn't center-scoped even though `AssociateAvailabilityBlock.center` is a required FK (no `AssociateLeave`-style `ALL_CENTERS` scope exists for blocks).
- Re-sync reconciles (user picked this over additive-only): per Google event id, diff against previously-imported active rows — unchanged (same center-set+time/day/reason) → skip (no write, no exception-scan rerun); new/edited → deactivate old + create fresh inside **one savepoint per event** (a mid-event overlap conflict on any center rolls back that whole event, never leaves a half-replaced state — this was a real bug caught mid-build, not a hypothetical); gone from Google → soft-deactivate (never hard-delete). Conflicts against a block from a _different_ source are skipped + counted, never silently dropped.
- Each created block still runs `apply_availability_exception_hooks(source_type=ASSOCIATE_BLOCK)` for parity with manual creation (flags appointments that now conflict).
- `last_synced_at` set only after a sync **succeeds** — not on every click/attempt.
- Model field additions (this session): `integrations.GoogleCalendarConnection.last_synced_at`, `appointments.AssociateAvailabilityBlock.google_event_id`. **No migration written/run by the agent** (repo rule above) — user runs `makemigrations`/`migrate`.
- FE (`Biopeak-Nexus-Admin-FE`): confirmed via Explore that **no Google Calendar UI exists at all yet** in this repo (not even for the shared-organizer flow) — this session builds the first one, inside `SettingsPage`, following its existing card/`createMutation`+`createQuery` hook/Zustand-auth-store patterns from scratch, not extending prior art.
- **Follow-up fix, same day:** `/callback/` no longer forwards raw `code`/`state` as URL params at all — signs `{code, state}` into one opaque ticket (`google_oauth.sign_oauth_redirect()`/`resolve_oauth_ticket()`, `django.core.signing`, 10-min expiry, no DB/cache row — stateless off `SECRET_KEY`, so no new infra/migration needed) and redirects `#t=<ticket>` only. `/complete/` + `/personal/complete/` now take `{"ticket": ...}` not `{"code": ...}`; `resolve_oauth_ticket()` checks `state` matches the endpoint (shared vs personal) so a ticket can't be replayed cross-flow. Bruno env var renamed `google_oauth_code` → `google_oauth_ticket` across both environments + all google_calendar/\*.bru files.
- **Real bug this caught:** FE's OAuth-callback hook was wired only into `ProtectedLayout`, but `ADMIN_FRONTEND_URL` points at `/`, which renders `<Login/>` — an already-authenticated user hits `Login.tsx:125-128`'s `<Navigate to={resolveLoginRedirect(...)} replace/>` _before_ `ProtectedLayout` ever mounts, dropping the URL hash. Fix: capture `#t=...` synchronously at `App.tsx` module scope (`captureGoogleCalendarOAuthTicket()`, same spot/pattern as the existing `hydrateFromToken()` call, i.e. before the router renders at all), stash into `sessionStorage`, strip the hash immediately. The `ProtectedLayout`-mounted hook now just consumes-and-clears that sessionStorage key once auth is confirmed, instead of reading `window.location.hash` itself.
- **Follow-up, same day — personal scope widened to read/write:** user explicitly asked to grant write upfront (not build write behavior yet, just avoid a future forced-reconnect). `PERSONAL_SCOPES` (`calendar.events.readonly`) removed; personal connect now requests the same `google_oauth.SCOPES` (`calendar.events`, full read/write) as the shared flow — `build_auth_url()` dropped its now-unused `scopes` override param entirely, single scope list only. Sync code itself (`availability_sync.py`) is unchanged and still only ever reads. If a write-back feature (e.g. mirror an associate's own appointments onto their personal calendar) gets built later, anyone who connected under the old read-only grant already has write scope too — no reconnect needed for that part.
- **Follow-up, same day — merged `/callback/` + `/complete/` into one view, user explicitly requested this (found the two-hop ticket relay unnecessarily complex).** `GoogleCalendarCompleteView`/`GoogleCalendarPersonalCompleteView` and the `/complete/`/`/personal/complete/` routes are deleted outright — `GoogleCalendarCallbackView.get()` (still `AllowAny`, still what Google's redirect hits) now does the entire rest of the job itself: exchange the code, fetch the email, resolve which flow + which user, save tokens, all before its own redirect back to the frontend. `google_oauth.sign_oauth_redirect()`/`unsign_oauth_redirect()` (the `{code, state}` ticket) are replaced by `sign_oauth_state()`/`unsign_oauth_state()` — now `state` itself (not a post-hoc ticket) carries `{"flow": "shared"|"personal", "user_id": ...}`, signed at `/connect/`/`/personal/connect/` time (still `django.core.signing`, still no DB row) and echoed back by Google unchanged. This is the _only_ way `/callback/` can know which Biopeak user a personal connection belongs to, since Google's redirect carries no JWT of its own — the shared flow doesn't need this (it resolves the user by email match, unchanged), but both flows sign `state` for consistency and so a tampered flow/user_id is rejected outright rather than silently trusted.
  - **Follow-up, same day — personal flow now requires the connected Google account's email to match the caller's own Biopeak login email, user explicitly requested this after confirming it reverses the original "any Gmail" design on purpose.** `_complete_personal_connection()` adds `if google_email.lower() != user.email.lower(): return "Connect the same Google account you log into Biopeak with.", None` after the existing `GOOGLE_CALENDAR_ID`-reserved check. Not a security fix — tokens already only ever save onto `request.user`'s own row regardless of which Google account is connected, so this adds no new protection against a hostile actor — it's a product policy so "connect your own calendar" stays literal. Known tradeoff, accepted explicitly: blocks staff whose personal Gmail differs from their Biopeak login email from using this feature at all.
  - **Follow-up, 2026-09-17 — two corrections to `availability_sync.py`'s "gone" detection and overlap handling, superseding lines 62/65 above.** (1) "Gone" no longer diffs against every imported block: a one-off block's `google_event_id` is only a deactivation candidate if `end_datetime > time_min` (recurring blocks are always candidates, unexcluded — they're only ever imported as never-ending `FREQ=WEEKLY` RRULEs, so a still-existing one always has an occurrence in the rolling window and keeps reappearing in every fetch; only an already-past one-off event ages out of Google's `timeMin` filter on its own). Without this, every already-ended one-off event got misreported as "removed" on the very next sync, even though nothing was deleted in Google — harmless for scheduling (already in the past) but wrong in the removed-count/log. Blocks created directly in Biopeak (`google_event_id=""`) were already excluded before this fix via `.exclude(google_event_id="")` and remain so. (2) `assert_associate_block_no_overlap()` is no longer called from this sync path at all — user confirmed Biopeak intentionally allows overlapping availability blocks, so a Google-imported block should never be rejected for coinciding with another block. The per-event savepoint + `skipped_conflicts` counter/`DRFValidationError` catch are removed along with it (nothing can fail there anymore); `create_associate_availability_block()` is still reused unconditionally. The `"skipped_conflicts"` key is dropped from `sync_google_events_to_availability_blocks()`'s return dict — confirmed via Explore no view/serializer/test read that key. Manual block creation (`appointments/serializers/__init__.py`) is untouched and still overlap-checked; this only affects the Google-import path.
  - Refactor bonus: the two nearly-identical Complete views' bodies collapsed into three small helpers in `views.py` — `_persist_connection()` (the upsert + stale-token-eviction logic, shared by both flows), `_complete_shared_connection()`, `_complete_personal_connection()` (each just resolves `(error, user)` for their own flow before handing off to `_persist_connection()`).
  - `/callback/`'s final redirect is now always just a plain outcome flag — `#gcal_connected=1` or `#gcal_error=<message>` (URL-encoded, human-readable, same text a JSON `detail` would have carried) — never a ticket, never the tokens, never the email. FE learns `google_email` later from `GET /google-calendar/` after re-fetching, not from the redirect.
  - FE: `capture-oauth-ticket.ts` renamed `capture-oauth-result.ts` (`captureGoogleCalendarOAuthResult`/`consumeGoogleCalendarOAuthResult`) — same "capture synchronously in `App.tsx` before the router mounts" pattern as before (still needed, same bug this guards against), just capturing a plain `{status: 'connected'} | {status: 'error', message}` instead of a ticket. `use-google-calendar-oauth-callback.ts` no longer calls any API at all — it just shows a toast and `queryClient.invalidateQueries(googleCalendarKeys.status)` directly. `useCompleteGoogleCalendarConnect` mutation and `googleCalendarApi.complete()` deleted — nothing left to call.
  - Bruno: `Complete.bru`/`PersonalComplete.bru` deleted; `Connect.bru`/`PersonalConnect.bru`/`Callback.bru` docs rewritten; both environments' `google_oauth_ticket` var replaced with `google_oauth_code`/`google_oauth_state` (for manually replaying the callback hop, now that there's nothing to paste into a second request).

---

## 2026-09-18 — Google Calendar push-notification webhook

- Adds real-time trigger for `sync_google_events_to_availability_blocks()` (personal calendars only, user explicitly confirmed — shared organizer's calendar is never watched, nothing reads busy time back from it). Previously the only trigger was a manual `POST /sync/` click. New: `POST /google-calendar/webhook/` (public, verified via channel id + resource id + channel token match instead of JWT — see `docs/google-calendar-integration.md`).
- **Blocked on a migration the agent cannot run** (repo rule above): `GoogleCalendarConnection` gained `watch_channel_id`/`watch_resource_id`/`watch_channel_token`/`watch_expires_at`. Confirmed via `makemigrations --check --dry-run` that exactly one migration is needed (`integrations`, adds those 4 fields) — not generated. New test file `integrations/tests/test_google_calendar_webhook.py` will fail with `UndefinedColumn` until the user runs `uv run manage.py makemigrations integrations && uv run manage.py migrate`.
- New setting `BE_SERVICE_BASE_URL` (`{DEV,STG,PRD}_` prefixed, `core/settings/*.py`) — user picked this name over a generic `BACKEND_BASE_URL` since no such setting existed anywhere in the repo before. Unset ⇒ channel registration is skipped outright (`google_calendar_webhook_configured()`), same "unconfigured means proceed unsynced" pattern as `GOOGLE_CALENDAR_ID` elsewhere.
- Renewal is a new management command, `renew_google_calendar_watch_channels` (user picked this over lazy-only renewal) — same style as `process_communication_outbox`, meant to run daily. Renewal is _also_ self-healed on every `POST /sync/` call regardless (`ensure_watch_channel_active()`), so the scheduled command isn't the only path — it just means renewal happens without anyone hitting `/sync/`.
- Google Calendar watch channels aren't renewable in place — `ensure_watch_channel_active()` always stops the old channel (best-effort) then creates a new one, never patches an existing one.
- Webhook notifications carry no event data (Google's Calendar push API is a bare "something changed, go look" signal) — the handler just re-runs the existing full-window sync, it doesn't do an incremental `events.list`. No `sync_token` column added; deliberately deferred as a possible later efficiency improvement, not a correctness gap.
- Webhook always responds 200, even for an unrecognized channel or a failed sync (`GOOGLE_SYNC_ERRORS`, logged) — a non-2xx makes Google retry with backoff and can eventually get a channel stopped outright.
- Bruno: added `google_calendar/Webhook.bru` (`auth: none`); `collection.bru`'s pre-request JWT-skip regex extended to also match `/google-calendar/webhook` (previously only `/webhooks/` and `/google-calendar/callback`).
- **Follow-up, 2026-09-18 — `watch_channel_token` removed, superseding line 85 above.** User judged the token redundant: `channel_id` is a server-minted `uuid.uuid4()` never exposed outside the Google<->server exchange, so the `find_connection_for_watch_channel()` match on channel id + resource id is already unguessable on its own — the extra token layered no real protection, and was further undermined by `GoogleCalendarWebhookView.post()` logging the full incoming request headers (which include `X-Goog-Channel-Token` itself). Removed `watch_channel_token` field (migration `0006_remove_googlecalendarconnection_watch_channel_token`), `channel_token_is_valid()`, the `token` sent to Google's `events.watch`, and the header check in the webhook view — verification is channel id + resource id match only now. Debug `print()`/`logger.info()` calls in `webhook_channel.py`/`views.py` intentionally left in place for now (user still testing).

---

## 2026-09-12 — Center associate list role filter

- `GET /centers/<uuid>/associates/?role=0|1` uses `Exists` on `AssociateCenterAssignmentRole`. Never `role_links__` JOIN — N active roles duplicated the assignment N times.

## 2026-09-12 — Care teams `members_live`

- `GET /centers/<uuid>/care-teams/?members_live=0|1`. `1` = every member live at center with mapped role active. `0` = ≥1 broken member (inactive user, inactive assignment, inactive/unmapped role link, inactive `AssociateRole`). Omit/junk = no filter. Independent of team `active=`. `Exists` on members, not JOIN. Same per-member live rules as booking `members_with_live_center_role`. Team always has ≥2 members (write + `members_count>=2`); filter does not special-case empty. `1` is not the bookable-team picker — booking still expands leftover live members.

---

## Non-obvious decisions

Pointers: appointments+availability → [`docs/appointments-frontend-api.md`](appointments-frontend-api.md). Google Calendar → [`docs/google-calendar-integration.md`](google-calendar-integration.md). Result fetch → [`docs/result-fetch-flow.md`](result-fetch-flow.md).

**API / tenancy**

- Customer associate list: `X-Center-ID` present → exclusive center filter; `center_id` query only if header absent. Role join against each returned customer-assignment center; keep nested roles; no multi-center fan-out.
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

- Onboarding completion only `CustomerProfile.is_onboarding_completed` (not Lead). Both `is_onboarding_sent` default `False`. `is_onboarding_completed` read-only on center home/detail. `is_invited` independent. Ready: lead `sent=True` and (no profile or profile incomplete).
- Leads writes `/leads/v2/` (POST create+shell, PATCH update+shell sync). v1 GET/POST/PATCH → 400; v1 DELETE still `/leads/{id}/`. `/auth/login-phone-direct/` = User lookup only, no shell.
- Emergency contact fields dropped from `CustomerProfile` + pre-consult baseline.
- Test kit: app `test_kit_inventory`. Global APIs, no `X-Center-ID`. One active kit/`CustomerProfile`. Eligible = completed pre-consult + no active kit. POST `/assign` `assigned_to` = non-empty profile UUID array; one txn; any fail → none; response `detail` only. `Product.is_assignable` default `False`. QC acks `qc_ack_packaging` / `qc_ack_all_components` write-gate on `Item`.
- Room/equip codes globally unique: `{EQ|RM}-{center.code}-{seq}`. Old `EQ-0005` rows keep format. Seq names stay `equipments_{center_id}` / `rooms_{center_id}`.
- `Service.name` unique catalog-wide, case-insensitive. `Room.name` unique per center, case-insensitive. Same row may keep name. Inactive rooms still occupy name. Existing dups block migrate.

**Diagnostics (Orange Labs)**

- App `diagnostics_orders`. National `CatalogItem` (`test_id` int unique). No city prices / category / fasting / pincode ranges.
- Create: `diagnostic_tests` = int array; Orange splits by `is_custom_package` — `False` → `tests:[{test_id:str}]`, `True` → `packages:[{package_id:str}]`. Local lines all `DiagnosticOrderLine.test_id`. Unique `(order_customer, test_id)`. Token never in FE.
- Auth: `IsAdminUser | IsAssociateUser` (no feature gate; `X-Center-ID` optional by design).
- Webhook `POST /webhooks/orange-labs/`: HMAC `X-OH-Signature` (raw body, SHA256 hex); idempotency `X-OH-Event-Id`; lookup `payload.request.city_request_id` (fallback `payload.order.city_request_id`); status = top-level `event`.
- Eligible customers: active + onboarding completed + active center assignment + no open (non-terminal) order. No program / pre-consult join.
- Migration `0005` first apply **wipes** diagnostics orders + catalog (irreversible; empty = no-op). Re-seed via `POST /add-test-package/`.

**Pre-consult**

- Envelope: `success` top-level only; never in `data`. `pre_consultation_response()` strips stray `success`.

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

- WhatsApp **not** in `products.Provider`. Env secrets only. Façade `integrations/communications/` → WhatsApp SDK + Google desired-state.
- Book/cancel/reschedule **enqueue only** via `transaction.on_commit` (`schedule_queue_*`). Outbox fail cannot roll back apt write. Missing env → skip that channel; apt still saves.
- Outbox `CommunicationOutbox` (`channel=whatsapp|google_calendar`). Worker `process_communication_outbox` (SQS wake + 10 min sweep). Claim via conditional `update` (no `select_for_update`). Stale WhatsApp `SENDING` → **SKIPPED**; stale Google `SENDING` → **FAILED** (retry). HTTP WhatsApp success w/o parsable `wamid` still ACCEPTED; max 2 attempts then SKIPPED.
- Unique `(appointment, channel, event_type)` for terminal events. Google coalesces one open row per appointment. Webhook `get_or_create` on `event_key`; `IntegrityError` → dup. Webhook `GET|POST /webhooks/whatsapp/`.
- Ops: SQS wake + EventBridge `rate(10 minutes)` `assets/scripts/sweep_jobs.sh`. Env `*_COMMUNICATION_OUTBOX_WAKE_QUEUE_URL`. **Not** in `deploy-aws.yml`.
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
