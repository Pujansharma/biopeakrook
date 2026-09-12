# Biopeak Nexus — Project Memory

Non-obvious decisions, agent prefs, traps. No code dumps. No CLAUDE.md / CODING_RULES.md clones. Specs live in `docs/`.

---

## User Preferences

- Code explain → clickable `[file.py:42](path/to/file.py#L42)` every mention, not prose-only.
- Never revert/alter code user manually edited. User change-back = final.
- Never `select_for_update()`. Ordinary ORM. No row locks.
- Never write migration files. Never `makemigrations`. User owns migrations.
- UUID detail URLs: `<uuid:pk>/`.
- No fn return/output type annotations unless asked.
- Prefer explicit `BaseModelSerializer` + `Meta.model` + declared fields. No `to_representation()` delegate.
- Keep related-object fields nested. Don't flatten.
- Don't repeat explicit `read_only=True` fields in `Meta.read_only_fields`.
- Never put derived service-document module-category props/display on model. Serializers compute code+label from `ServiceResult.document_type`.
- API add/change → update `bruno/` same change. Source of truth = `bruno/`. Envs: `bruno/environments/{Development,Production}.bru`. No folder vars (folder > env → blank tokens).
- **Bruno auth (2026-09-12):** 401 `"Authorization header must contain two space-delimited values"` = empty Bearer. Empty runtime `access_token` masks env. Never `auth: bearer` + `{{access_token}}`. Collection `bruno/collection.bru` pre-request sets `Authorization` from env → collection → runtime (skip empty; skip `/webhooks/` + Google callback). Requests/folders `auth: inherit`. Pre-consultation folder overwrites w/ `customer_access_token`. Login Phone Direct: `bru.deleteVar('access_token')` before set. Empty optional query → `~param:`.
- **Bruno Find Slots (2026-09-11):** `POST .../appointments/slots/` preferred keys `room_id`, `care_team_id`, `doctor_id`, `specialty_id`. `health_coach_id` → 400. Empty interpolated UUIDs strip in pre-request. `care_team_id` XOR `doctor_id`/`specialty_id`. Env: `slot_date`, `doctor_id`, `specialty_id`.
- List filter query = `active=0|1`. Model/body/response stays `is_active`. Never `is_active` as query name.
- Center resource lists (associates + v2 room-types / equipment-types / rooms / equipment / services): omit `active` → both. `active=0|1` still filters. Availability lists default-active-only.
- Don't send empty UUID query params. Disable w/ `~room_type_id: {{room_type_id}}`. Junk UUID on rooms list → 400 `"Invalid room_type_id."`
- **Rooms `type_active`:** `GET /centers/<uuid>/v2/rooms/?type_active=0|1`. `1` = `room_type_ref` set + `RoomType.is_active`. `0` = type null or inactive. Omit/junk = no filter. Independent of room `active=`.
- **Equipment `type_active` + `room_allotted`:** `GET /centers/<uuid>/v2/equipments/?type_active=0|1&room_allotted=0|1`. Independent AND. `type_active` same as rooms. `room_allotted=1` = `room` set + `Room.is_active`. `0` = room null or inactive. Omit/junk = no that filter. Independent of equipment `active=`.
- **Success envelope (mandatory):** `{detail, data}` via `send_response` / `response_format` / `Base*APIView`. `data` = object, list, or omit. Never top-level array. Never nest `{detail, data}` inside `data`. Never raw `Response(payload)`. List-creates: `data` = array; client uses `data[0].id`. No `success` key (pre-consult only). Custom list-create: override `post()` + `send_response(..., status=201)`. Do **not** `send_response` inside `create()` on `BaseListCreateAPIView` → nested envelope.

---

## 2026-09-11 — Multi-role associates, multi room types, preference-only booking

- Migrations: `associates.0020` drop `AssociateCenterAssignment.role`, add `AssociateCenterAssignmentRole`; `services.0008` drop `CenterServiceAssignment.required_room_type`, add `CenterServiceRoomTypeRequirement`; `appointments.0019` `AppointmentAssociate` UniqueConstraint `(appointment, associate)`. Schema bootstrap removed from tests.
- Associate API hard-break: write `role_ids[]` only; response `role_ids` + `roles[]`; no singular `role`/`role_id`. Admin still cannot get care roles. RBAC `AssociateFeaturePermission` = OR across multi-roles.
- `CustomerAssociateSerializer` exposes `roles`/`role_ids` from `current_center_assignment` through-links.
- Care team member still one `role_id` per row; role must be ∈ associate's live roles at center.
- Slots/book/reschedule: preference mandatory for preferred path; no leftover auto-fill from service role/room pools. Staff+room from preferred or pin only. `health_coach_id` → 400 use `specialty_id`. `doctor_id` = live role name contains doctor; `specialty_id` = live non-doctor. Same person both → 400. Dup associate on apt → 400 (+ DB unique).
- Room types on assignment: OR eligibility. Write via `RoomType.filter_active(center=...)`. Center service V2 write/read `required_room_type_ids[]` (not singular).

## 2026-09-12 — Center associate list role filter

- `GET /centers/<uuid>/associates/?role=0|1` uses `Exists` on `AssociateCenterAssignmentRole`. Never `role_links__` JOIN — N active roles duplicated the assignment N times.

---

## Non-obvious decisions

Pointers: appointments+availability → [`docs/appointments-frontend-api.md`](appointments-frontend-api.md). Google Calendar → [`docs/google-calendar-integration.md`](google-calendar-integration.md).

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
- Program UID: `P`-prefix ≥4-digit sequence on active therapy+composite create; API `uid` read-only; nullable; no DB unique. `backfill_program_uids` **not run yet**.
- `ServiceResult` belongs to `ProgramService`. Module-category on serializer, not model. Unmapped → `unknown`. Invalid `module_category` query → no rows.
- Counters persist via ORM subquery (include inactive/cancelled); API reads never annotate. Repair: `recompute_service_document_counts`.
- ProgramService cancel: active flag + audit only; result/doc rows unchanged. Therapy cancel needs `X-Center-ID`. Legacy last-service writes parent cancel metadata w/o deactivating parent/subtype.

**Leads / onboarding / inventory**

- Onboarding completion only `CustomerProfile.is_onboarding_completed` (not Lead). Both `is_onboarding_sent` default `False`. `is_onboarding_completed` read-only on center home/detail. `is_invited` independent. Ready: lead `sent=True` and (no profile or profile incomplete).
- Leads writes `/leads/v2/` (POST create+shell, PATCH update+shell sync). v1 GET/POST/PATCH → 400; v1 DELETE still `/leads/{id}/`. `/auth/login-phone-direct/` = User lookup only, no shell.
- Emergency contact fields dropped from `CustomerProfile` + pre-consult baseline.
- Test kit: app `test_kit_inventory` (legacy inventory/assignment tables dropped). Global APIs, no `X-Center-ID`. One active kit/`CustomerProfile`. Eligible = completed pre-consult + no active kit. POST `/assign` `assigned_to` = non-empty profile UUID array; one txn; any fail → none; response `detail` only. `Product.is_assignable` default `False`. QC acks `qc_ack_packaging` / `qc_ack_all_components` write-gate on `Item`.
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
- Customer overlap GiST **global** (any center) on busy exclusive range. Python busy map: customer, no center filter.
- Slot/book IDs: `customer_profile_id` / `service_id` vs this center's active assignment. Miss/inactive/other-center → 400 `"Invalid customer profile for this center."` / `"Invalid service for this center."` (no existence oracle).
- Slots return **one pinned combo** per start/end. Book/reschedule: pin validates (no re-pick); omit pin → resolve from `preferred`. Incomplete pin (associates w/o `room_id` for in_person) → 400, never silent re-resolve. Invalid pin `room_id`/`equipment_id` → 400 not 404. `preferred.care_team_id` XOR doctor/specialty. Pref person outside service roles → extra, not 400. Pref room overrides service room type. in_person always needs room else 400. First active equipment on room only.
- `Appointment.notes` writable on book/reschedule; omit/`null` on reschedule keeps existing; `""` clears. Not passed raw to Google — wrapped via `build_appointment_*_notes()`.
- List `?search=`: customer name/email/phone, apt `code`, service name. `search` w/o `start` = all dates, newest first. Hard-cap 500. `associate_id`/`role_id` match `associates[]`; together = **OR**.
- Exceptions `status` query `open`|`resolved`; junk → 400.
- Care team: name unique per center case-insensitive. Member write rejects inactive `AssociateRole` (`400` `"Role is inactive."`). Expand live assignment does **not** 400 when team misses a service role — leftover roles searched. Empty live members + preferred/pin `care_team_id` → 400 `"Care team has no live members at this center."`.
- Availability: PATCH `is_active=false`; no DELETE. Recurring POST `days_of_week` `"0"`…`"6"` → 1 row/day; 201 `{detail, data}` `data` = list. Assoc one-off = datetimes; room/equip one-off + downtime = `date`+`start_time`+`end_time` (`settings.TIME_ZONE`). `scope=all_centers` leave stores `center=null`. Leave wins vs associate block. Downtime wins vs room/equip block.
- Roster ⊆ center hours: write 400 if before open / after close / closed day / missing hours. Hours PATCH 400 if shrink/close would leave active roster outside. Codes: `before_opening`, `after_closing`, `center_closed`, `center_hours_missing`, `roster_on_closed_day`. Inclusive edges. Existing out-of-range rows stay until next save. Roster POST/PATCH enqueues async `associate_roster` scan; response top-level `exception_scan`.
- Care-team calendar base = intersect live members' (center ∩ roster). Team blocks subtract from member associate calendars + slots + ops capacity. Overlap only vs other active blocks on **same** team. `ExceptionSourceType.CARE_TEAM_BLOCK` matches `Appointment.care_team` only (not solo member apts). `PATCH is_active=false` also soft-deactivates that team's active blocks; reactivate does not revive. One-off ExclusionConstraint; recurring Python-only.

---

## Communications / Google Calendar traps

Canonical: [`docs/google-calendar-integration.md`](google-calendar-integration.md).

- WhatsApp **not** in `products.Provider`. Env secrets only. Façade `integrations/communications/` → WhatsApp SDK + Google desired-state.
- Book/cancel/reschedule **enqueue only** via `transaction.on_commit` (`schedule_queue_*`). Outbox fail cannot roll back apt write. Missing env → skip that channel; apt still saves.
- Outbox `CommunicationOutbox` (`channel=whatsapp|google_calendar`). Worker `process_communication_outbox` (SQS wake + 10 min sweep). Claim via conditional `update` (no `select_for_update`). Stale WhatsApp `SENDING` → **SKIPPED**; stale Google `SENDING` → **FAILED** (retry). HTTP WhatsApp success w/o parsable `wamid` still ACCEPTED; max 2 attempts then SKIPPED.
- Unique `(appointment, channel, event_type)` for terminal events. Google coalesces one open row per appointment. Webhook `get_or_create` on `event_key`; `IntegrityError` → dup. Webhook `GET|POST /webhooks/whatsapp/`.
- Ops: SQS wake + EventBridge `rate(10 minutes)` `assets/scripts/sweep_jobs.sh`. Env `*_COMMUNICATION_OUTBOX_WAKE_QUEUE_URL`. **Not** in `deploy-aws.yml`.
- Google: one fixed shared organizer (`GOOGLE_CALENDAR_ID`). Resolve via `Associate.google_email__iexact` + `is_active` + live `google_refresh_token` (not email alone — disconnect keeps `google_email`).
- Sync best-effort async. Never Google HTTP on request path. `GOOGLE_SYNC_ERRORS` = `(requests.RequestException, ValueError, InvalidToken, ImproperlyConfigured)` — exclude `KeyError`/`TypeError` (our bugs must crash).
- Event id = appointment UUID hex. Book title `"Appointment Confirmed"`; reschedule `"Appointment Rescheduled"`. Cancel does **not** clear `google_event_id`/`google_meet_link`. Leave virtual → clear Meet (`clear_meet_link=True`). Insert/patch success then `appointment.save` `DatabaseError` → log+swallow; do **not** delete Google event.
- `/connect/` + `/complete/` public (`AllowAny`); never read `request.user`. `/complete/` rejects unless Google email equals `GOOGLE_CALENDAR_ID`; then match `Associate.user.email` (both active). `google_email` uniqueness case-insensitive (`Lower`). Stale email on other associate → evict first; `IntegrityError` → 400.
- Disconnect: clear tokens, **keep** `google_email`. "Connected" = `google_refresh_token`, not `google_email`. Disconnecting the shared organizer requires `is_active` + `is_admin` on ≥1 active center assignment (403 else). `InvalidToken` on decrypt → clear tokens, no 500.
- Clear tokens only on Google `invalid_grant` (`google_oauth.is_invalid_grant_error`). Other 400 (`invalid_client`/`invalid_request`) must not wipe tokens. `/complete/` fail-fast if client secret or encryption key missing **before** `exchange_code` (code is one-time). `revoke_token()` no-op only on 400; other non-OK raise. Disconnect lets revoke `RequestException` → 503 (don't mark disconnected while Google grant live).
- Virtual Google description = Meet-join line, no clinic address. Other modality = `Center.full_address` (computed, not a column). Dead HTML email path deleted; Google invite = only customer-facing notify.

---

## Conventions (not in CODING_RULES.md)

- ORM lookups in serializers/utils: `filter(...).first()`. No `.get()`; handle missing explicitly.
- Serializer add/remove: write-only `{id}` lists; pop w/ `[]` fallback; one query + set diff; save → remove before add → refresh counts → return.
- Views: `*ViewMeta` + `filter_kwargs = {}` on `BaseGenericAPIView`. No standalone queryset utils. No `http_method_names`. Serializers never import ViewMeta querysets. `utils/db.py` = mutations only. Representation uses prefetched `to_attr`.
- Serializer `create()`/`update()` own persistence. Views pass context to `serializer.save(...)`; must not capture return, assign `serializer.instance`, or reload for write-response. Route getters take no id args; resolve `self.kwargs["pk"]` via `get_object_or_404`. Shared `*ViewMeta` only if `pk` same resource type. Create needing nested prefetch: reload via ViewMeta queryset → `serializer.instance`.

---

## Tooling

**django-debug-toolbar v7:** `include("debug_toolbar.urls")` OK. `CompressedManifestStaticFilesStorage` needs `collectstatic` or toolbar.js null `dataset`. Fix: `uv run manage.py collectstatic` after upgrade.
