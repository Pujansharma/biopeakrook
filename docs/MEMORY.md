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
- `get_valid_access_token()` `invalid_grant`: re-read row; retry once if `google_refresh_token` changed; only `clear_google_calendar_tokens()` when the token we sent is still stored.

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
- Disconnect/status/refresh: `IsAdminUser | IsAssociateUser`. Clear tokens, **keep** `google_email`. "Connected" = `is_active` + `google_refresh_token`. Soft-off row: status/refresh disconnected; disconnect still revokes leftover tokens. Shared-organizer disconnect: platform `Admin` OK; associate needs `is_active` + `is_admin` on ≥1 active center assignment (403 else). `InvalidToken` on decrypt → clear tokens, no 500.
- Clear tokens only on Google `invalid_grant` (`google_oauth.is_invalid_grant_error`) when the refresh token we sent is still the stored one. Concurrent worker rotated the grant → re-read + retry once, do not wipe. Other 400 (`invalid_client`/`invalid_request`) must not wipe tokens. `/complete/` fail-fast if client secret or encryption key missing **before** `exchange_code` (code is one-time). `revoke_token()` no-op only on 400; other non-OK raise. Disconnect lets revoke `RequestException` → 503 (don't mark disconnected while Google grant live).
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
