# Biopeak Nexus — Project Memory

---

## User Preferences

- Never revert/alter code user manually edited. User change back = final. Don't touch those lines unless asked.
- Never `select_for_update()`; ordinary ORM querysets, no row locks.
- Never create Django migration files manually, never run `makemigrations`. User owns migrations.
- Always `<uuid:pk>/` for UUID detail URL path params.
- No function return/output type annotations unless user asks.
- Prefer explicit `BaseModelSerializer` + `Meta.model` + declared fields over `to_representation()` delegating to another serializer.
- Keep related-object fields nested; don't flatten to top level.
- Don't repeat explicit `read_only=True` fields in `Meta.read_only_fields`.
- "update collection" / "update bruno" → update `bruno/` (requests, folders, envs).
- API collection source of truth is Bruno at `bruno/`. Envs: `bruno/environments/{Development,Production}.bru`. Folder vars omitted so they cannot shadow env tokens.
- **Always add or update Bruno** (2026-08-26): API add/change → update `bruno/` same change. Never miss.
- **List active filter query param** (2026-08-27): `active=0|1` on list endpoints. Model/DB/body/response field stays `is_active`. Never `is_active` as query param name.
- **Center resource list GET omit active** (2026-08-28): associates + v2 room-types / equipment-types / rooms / equipment / services list omit `active` → both. `active=0|1` still filters. Availability lists default-active-only.

---

## Architecture Decisions

| Decision | Reason |
|---|---|
| On-demand slot generation (no pre-stored slots) | No DB bloat; compute at query time. *(Legacy `appointments/utils/intervals.py` removed 2026-08-25 — rebuild later.)* |
| Appointments app emptied (2026-08-25) | Unused booking models + engine removed. `AppointmentModes`/`AppointmentDays` → `core/utils/constants.py`. Dropped `EquipmentBooking.appointment`. App stayed in `INSTALLED_APPS` as empty shell then rebuilt. User owns drop migrations. |
| UUID7 PKs all models | Better DB perf + time-sortable |
| Bruno collection at `bruno/` (2026-08-18) | Sole API collection. Open `bruno/` in Bruno. Envs: `bruno/environments/Development.bru`, `Production.bru`. No folder vars (folder > env, would blank tokens). |
| Center operating hours + closures write APIs (2026-08-26) | Canonical `/centers/<uuid>/availability/operating-hours/` (GET/PATCH bulk upsert) + `/closures/` (GET/POST + PATCH soft reopen). `CenterClosure.type`=`holiday`\|`manual` + `reason`. Center calendar default `granularity=week`. Availability URL `<uuid:center_id>` so resource detail `pk` no collide. |
| Center isolation via `X-Center-ID` | Multi-tenant |
| Customer associate list center precedence (2026-08-19) | `CustomerAssociateListView`: optional `X-Center-ID` + `center_id` query. Header present → exclusive center filter; query IDs only if header absent. |
| Customer associate list role join (2026-08-19) | Filter intermediate associate-center assignment against each returned customer-assignment center before picking role. Keep nested `role`; no multi-center join fan-out. |
| `uv` sole package manager | Faster, reproducible; replaces pip |
| All docs in `docs/` | `CODING_RULES.md` |
| Composite template SKU (2026-08-19) | `CompositeTemplate.code` required unique user-entered SKU; no sequence UID. Nested template refs use `BaseCompositeTemplateSerializer` (`id`,`code`,`name`,`is_active`). Full `CompositeTemplateSerializer` for template CRUD. User owns UID-removal migration. |
| Pre-consultation schema 3.0.0 (2026-06-30) | Normalized 15-table session-scoped model: `PreConsultationCategorySelection`, `PreConsultationConcern` (+ symptom/source/family/probe), `PreConsultationMedicalHistory` (+ diagnosis/allergy/surgery/medication/sexual-health), `PreConsultationLifestyleAnswer`, `PreConsultationHealthGoal`. Session: `directive_schema_id`, `current_layer`. Taxonomy: category/concern/symptom/concern_source/age_band. Layer ids: `patient_category`, `patient_concern`, `patient_symptom`, `patient_concern_probe`. Cascade reset `layers/reset.py`. Squashed `0001_initial`. |
| Pre-consultation envelope (2026-06-30) | `success` top-level only; never in `data`. `pre_consultation_response()` strips stray `success`. |
| Program ERD direction (2026-06-11) | Keep domain `Client`. `Service` + type/products. Composites from ERD. Reusable services; center via `CenterServiceAssignment`; qty on `ProgramService`; assessment via provider/product callbacks. |
| ProgramService shared + therapy split (2026-06-12 / 2026-07-27) | Ordinary + composite use `ProgramService` line: keep `sessions_count`/`sessions_used`/`sessions_cancelled`; no rename/aliases; `sessions_count=0` = unlimited (no positive check). `TherapyProgram.program` PK; `TherapyProgramService.program_service` PK; therapy runtime (`redeem_code`) + `RedemptionHistory` → `TherapyProgramService`. Cancel/`RedemptionHistory` only if `Program.program_type` is `THERAPY`. `wellness_*` = API aliases only. One `CompositeProgramSerializer`; `create()` returns `CompositeProgram` direct. Object checks in `create()`/`update()`; no return annotations on `SerializerMethodField`. User owns migrations. |
| Composite prerequisites (2026-07-29) | `CompositeServicePrerequisite` singleton on `CompositeTemplateService`. `BaseModel`; empty `related_services` OK; default `require_any`; ORM `related_services_count`. Responses: prerequisite meta + 3-service preview. `PUT programs/composites/services/<template_service_uuid>/prerequisites/`; paginated `prerequisites/<uuid>/prerequisite-services/` + `available-prerequisite-services/`. |
| Composite program counters (2026-08-05) | ORM add-on + category counts on `CompositeProgram`. Category = template + add-ons; `add_ons_count` overlaps categories. Parent `Program.services_count` authoritative; counts include inactive/cancelled. |
| Repeatable composite add-ons (2026-08-14) | Assessment + therapy add-on selection via category catalogue APIs. `POST programs/composites/add-ons/` keeps repeated `add_services`; returns refreshed composite-program w/ limited preview + counts. Authoritative paginated list: `profiles/<profile_uuid>/programs/composite-program-services/`, filter `service_category` + `assignment_type`; consultations excluded. Add-ons don't change pricing or inherit template prerequisites. Spec: `docs/composite-program-add-ons-frontend-eprd.md`. User owns constraint-removal migration. |
| Program UID (2026-08-05) | Active therapy + composite creates: `P`-prefix, ≥4-digit sequence UID in same txn. API `uid` read-only. Nullable; no DB unique. `backfill_program_uids` one-row-at-a-time; not run yet. |
| Test kit inventory merge (2026-08-06) | `test_kit_inventory` absorbs `product_inventory` + `test_kit_assignment`. Legacy drop `0002_remove_legacy_inventory_and_assignment_tables`. APIs `/test_kit_inventory/` (specs, consignment, all, batches, customer, assign, assignment-history, providers/add, products/add). Native `Provider`/`Product`/`Batch`/`Item`/`Assignment` — no `tags.type` filter. One active kit/`CustomerProfile`; assignee = profile id. Eligible = completed pre-consult + no active kit. Global APIs (no `X-Center-ID`). Spec: `docs/superpowers/specs/2026-07-30-test-kit-assignment-design.md`. Bruno: `bruno/test_kit_inventory/`. |
| Test kit multi-assign (2026-07-31) | POST `/assign` `assigned_to` = non-empty profile UUID array. N rows, one atomic txn; any fail → none created. Response = success `detail` only (no `data`). Model unchanged. Spec: `docs/superpowers/specs/2026-07-31-test-kit-multi-assign-design.md`. |
| Product `is_assignable` (2026-08-06) | Default `False`. Only `True` assignable. Specs `?is_assignable=0\|1`; payload + create optional; assign rejects non-assignable. |
| Product QC acks (2026-08-04) | `qc_ack_packaging` / `qc_ack_all_components` write gate + persist on `test_kit_inventory.Item`. |
| Product inventory specs test_kit filter (2026-08-06) | ~~`GET /product_inventory/specs/` `tags.type == "test_kit"`~~ superseded by inventory merge same day. Spec: `docs/superpowers/specs/2026-08-06-product-inventory-specs-test-kit-design.md`. |
| Service result documents (2026-08-07) | `ServiceResult` belongs to `ProgramService`. Shared result data, immutable upload/fetch mode, result-level document type; many `ServiceDocument` files (file + report/raw category). |
| Customer profile document list (2026-08-17) | `GET /profiles/<uuid:pk>/documents/` paginated across all programs owned by profile, no center scope. Admins/associates any profile; customers own-account only. Search filename/provider/product/service; filter active, result document type, report/raw, inclusive sample-collection dates. ProgramService ref exposes nullable composite-program + composite-template meta. Spec: `docs/customer-profile-documents-frontend-eprd.md`. |
| Product allowed-document metadata (2026-08-07) | `GET /products/<uuid:pk>/allowed-documents/` static provider/product `ServiceDocumentType` choices; `Other` always last. Specialized codes: blood, OligoScan, SOMFIT, MetSights PP, EVO 360, urine-metabolite, salivary-cortisol. MetFlux = sole provider callback for MetSights Precision Plus. User owns provider/choice migrations. |
| Assessment result upload selection (2026-08-10) | Assessment ProgramService selectors: active providers/products/assignments only; reject inactive ProgramServices. Result create needs eligible product + allowed document type. Product/type editable until first linked document; dates stay editable. Upload: one file + report/raw; no finalize API. |
| Persisted service result and document counters (2026-08-12) | `ServiceResult.documents_count` = direct docs. `ProgramService`: `results_count` + `documents_count`/`reports_count`/`raw_data_count` from docs across results. Refresh all three together via ORM subquery; no active filter; API reads never annotate. `recompute_service_document_counts` repairs. |
| Composite program result and document counters (2026-08-19) | `CompositeProgram` persists `results_count`, `documents_count`, `reports_count`, `raw_data_count` across every assigned `ProgramService` (add-ons + inactive/cancelled). Create/delete hooks refresh ORM subqueries. Staff/add-on/customer composite responses expose read-only. `recompute_service_document_counts` repairs. User owns migration. |
| Program-service cancellation endpoints (2026-08-12) | Assessment/therapy/consultation `POST .../<uuid:pk>/cancel/`. Touches ProgramService active flag + audit only; result/document rows unchanged. Therapy alone needs `X-Center-ID` + session/history effects. Legacy last-service rule writes parent Program cancel metadata w/o deactivating parent/subtype. |
| Lead/profile onboarding (2026-08-06) | Drop `Lead.is_onboarding_completed`. Completion only `CustomerProfile.is_onboarding_completed`. Both `is_onboarding_sent` default `False`. Lead POST/PATCH + center create/profile PATCH writable `is_onboarding_sent`; `is_onboarding_completed` read-only on center home/detail. Login shell copies `lead.is_onboarding_sent`. Lead PATCH syncs linked profile. `is_invited` independent. Ready: lead `sent=True` and (no profile or profile incomplete). |
| Leads API v2 (2026-08-10) | Admin writes `/leads/v2/` (POST create+shell, PATCH update+shell sync). v1 GET/POST/PATCH → 400; v1 DELETE still `/leads/{id}/`. Bypass login `/auth/login-phone-direct/` = User lookup only, no shell. No legacy backfill. Bruno: `bruno/leads/`. |
| Emergency contact dropped (2026-08-07) | Removed `CustomerProfile.emergency_contact_name` / `emergency_contact_phone`. Pre-consult baseline no longer R/W those. |
| Diagnostics / Orange Labs (2026-08-11+) | App `diagnostics_orders`. National catalog `CatalogItem` (`test_id` int unique, `name`, `price`, `is_custom_package` default `False`, `description` blank default `""`). No `CatalogCityPrice` / category / fasting / pincode ranges. `GET /test-packages/?search=` → `{tests:[{test_id,name,price,is_custom_package,description}]}`. `POST /add-test-package/` create-only (`test_id`,`name`,`price`; dup `test_id` → 400). Create: `diagnostic_tests` = int array; Orange `tests:[{test_id:str}]`, `packages:[]`. Dropped order `city` + list `?cities=`. Optional denorm `pincode` from address (no gate). `tat_in_hours` null on new orders. Order detail `tests` only (no `packages`). `DiagnosticOrderLine` UniqueConstraint `(order_customer, test_id)`. Multi-patient; token never in FE. SDK `integrations/orange_labs/sdk.py`. Webhook `webhooks/orange_labs/`. Auth: `IsAdminUser | IsAssociateUser` (no feature gate; any associate JWT OK; `X-Center-ID` optional by design). Env `*_ORANGE_LABS_API_BASE_URL` / `*_ORANGE_LABS_API_KEY` / `*_ORANGE_LABS_WEBHOOK_SECRET`. Dropped `order_link` + `raw_create_request`; keep `raw_create_response`. Create: plain address; gender `Gender.MAPPING` (`Male`/`Female`/`Other`); API `age` int, Orange payload `age` string. Webhook `POST /webhooks/orange-labs/`: HMAC `X-OH-Signature` (raw body, SHA256 hex) + secret; idempotency `X-OH-Event-Id`; lookup `payload.request.city_request_id` (fallback `payload.order.city_request_id`); status = top-level `event`. On `test.completed_sent` / `order.completed` merge slim reports by `id` (`file_type`, `file_name`, `tokenize_public_file_url`). `DiagnosticOrderRescheduleHistory` after Orange reschedule; denorm `last_reschedule_*` + `total_rescheduled`; nested `reschedule_history` on `GET .../order/<request_id>/` only. Migration `0005`: on first apply only, wipe all diagnostics orders + catalog + city prices + summary (irreversible; empty = no-op), then national schema. Re-seed catalog via `POST /add-test-package/` after deploy. Bruno: `bruno/diagnostics_orders/` (admin\|associate JWT; no feature gate; optional `X-Center-ID`). User owns migrations. |
| Diagnostics eligible customers (2026-08-20) | List + create share: `CustomerProfile.is_active`, `is_onboarding_completed`, active `center_assignments`, exclude open (non-terminal) diagnostics orders. No program check, no `pre_consultation_session` join. |

---

## Known Issues / In-Progress Work

**DRF nested as_view() (2026-08-31)** — Never `SomeView.as_view()(request)` from another DRF view. Outer dispatch already wrapped `request` as `rest_framework.request.Request`; inner `as_view()` re-wraps → `AssertionError` 500. Dispatch via view instance handler (`dispatch_to_view` in `appointments/views/booking.py`). Hit GET list + POST book on `AppointmentCollectionView`.

**Center care teams (2026-09-01)** — Spec `docs/superpowers/specs/2026-09-01-center-care-teams-design.md`. Code in `appointments`: `CenterCareTeam` + `CenterCareTeamMember`; `Appointment.care_team` nullable PROTECT. Catalog `/centers/<uuid>/care-teams/`. Slots: `preferred.care_team_id`. Book/reschedule: top-level `care_team_id` XOR `associates`. User owns migrations. Testing out of scope. Bruno: `bruno/appointments/care-teams/`.

**Appointments booking design (2026-08-28)** — Spec `docs/superpowers/specs/2026-08-28-appointments-design.md` (production-ready 5/5). Plan `docs/superpowers/plans/2026-08-28-appointments.md` (16 tasks, 4 phases). User owns migrations (`btree_gist` first). Bruno: root `appointments/` + move `availability/`. Testing out of scope. **Lifecycle (2026-08-28):** cancel + reschedule allowed from `checked_in` (waiting room); reschedule lands `confirmed`. `in_progress` still blocks cancel/reschedule (ack-only exceptions). No-show remains `confirmed` only.

**Availability system (2026-08-26)** — `appointments/`: roster, associate/room/equipment **blocks** (one-off + recurring), associate leaves (`center`\|`all_centers`), room/equipment **downtimes** (one-off only). Calendars: `/centers/<uuid>/availability/` (+ resource paths) + `/associates/<uuid>/availability/`. CRUD under center availability; PATCH `is_active=false`; no DELETE. **Hours/closures:** `GET/PATCH .../operating-hours/` bulk upsert; `GET/POST .../closures/` + `PATCH .../closures/<uuid:pk>/` soft reopen. `CenterClosure.type`=`holiday`\|`manual` + `reason`. Calendar event `closure`. Center calendar default `granularity=week`. URL `<uuid:center_id>` avoid pk collide. **Roster bulk:** `POST/PATCH .../associates/<id>/roster/` (`entries`, int 0–6). POST additive (omit = leave). PATCH week-diff (omit = `is_active=false`); empty entries rejected. GET `.../associate-roster/?associate=`. **Blocks (assoc/room/equip):** resource in URL. Recurring POST `days_of_week` `"0"`…`"6"` → 1 row/day, list res; no `effective_until` → deactivate `is_active=false`. Assoc one-off = datetimes; room/equip one-off + downtime = `date`+`start_time`+`end_time` (same day, `settings.TIME_ZONE`). Leaves: `associates/<id>/leaves/` — associate + center from URL; `scope=all_centers` stores `center=null`. **Calendar query scope (2026-08-27):** collectors filter blocks/leaves/downtimes to query window (recurring by `effective_from`/`effective_until`; one-offs by datetime/date overlap); operating hours `is_open=True` only. API contract unchanged. **Overlap:** `appointments/utils/overlap.py` (blocks↔leaves/downtimes). Leave always wins vs associate block: leave may overlap existing block; block cannot be created on top of leave. Downtime always wins vs room/equipment block: downtime may overlap existing block; block cannot be created on top of downtime. Perms v1: `IsAdminUser|IsAssociateUser` + center/`X-Center-ID`. Engine: `intervals.py`+`calendar.py`. Docs `docs/availability.md`. Bruno `bruno/centers/availability/` (to move to root `bruno/availability/` with appointments work). ponytail: TZ=`settings.TIME_ZONE`; room/equip base=center hours. **User owns migrations.**

**Center inventory + service resources v2 (2026-08-25)** — Spec `docs/superpowers/specs/2026-08-25-center-inventory-service-resources-design.md`; plan `docs/superpowers/plans/2026-08-25-center-inventory-service-resources.md`. Code: `accounts/centers/v2/` under `/centers/<uuid>/v2/`. Phase A dual-field (CharField enums kept + `Room.room_type_ref` / `Equipment.equipment_type` FKs). `RoomType`/`EquipmentType` per-center. Assignment fields + `CenterServiceRoleRequirement` on `CenterServiceAssignment`. No DELETE; PATCH `is_active`. Associates: `X-Center-ID` must match URL. Bruno: `bruno/centers/v2/`. **User owns migrations** — run makemigrations for inventory + programs.services.

**Room/equipment codes (2026-08-27)** — `Equipment.code` / `Room.code` globally unique. Old per-center seq emitted `EQ-0005` / `RM-0005` → collide across centers. Generators now `{EQ|RM}-{center.code}-{seq}` (e.g. `EQ-CT-0001-0001`). Sequence names stay `equipments_{center_id}` / `rooms_{center_id}`. Existing `EQ-0005` rows keep old format. No migration.

**CenterServiceAssignment bridge (2026-05-11)** — ✅ code (services/, external/); task `docs/tasks/center-services-bridge-model.md`. Pending: migrate + run.

**External centers count (2026-05-11)** — ✅ `CustomerProfile.external_centers_count`; inc/dec `accounts/customers/utils/db.py`; `recompute_external_centers_count`.

**Email/phone split (2026-05-12)** — ✅ COMPLETED. Staff `contact_phone` (not `user.phone`); customer `contact_email` (not `user.email`). Create: admin/associate `phone=None`+email; customer `email=None`+phone. Validate via `check_admin_associate_user_exists()` / `check_customer_user_exists()`. Updates pop unwanted fields. Admin list/search/fieldsets updated.

---

## Tooling Notes

**django-debug-toolbar v7 (2026-06-20)**
- `include("debug_toolbar.urls")` OK v6→v7
- `CompressedManifestStaticFilesStorage` needs `collectstatic` or toolbar.js null `dataset` error
- Fix: `uv run manage.py collectstatic` after upgrade

---

## Conventions Established Through Collaboration

**Naming (2026-05-11)** — No abbreviations (`count` not `cnt`, `assignment` not `asg`). Explicit brief formal names. In `CODING_RULES.md` §1.

**Django FK (2026-05-18)** — Never `<field>_id`; always relation `.pk`. In `CODING_RULES.md` §11.

**ORM lookups (2026-07-27)** — `filter(...).first()` in serializers/utils. No `.get()`; handle missing explicitly.

**Serializer add/remove (2026-08-04)** — Write-only `{id}` lists; pop w/ `[]` fallback; helper validates IDs vs parent scope (one query + set diff), raises on field, bulk `add()`/`remove()`. `create()`/`update()`: save → remove before add → refresh counts → return. No dup validation in create/update.

**View querysets (2026-07-27)** — `*ViewMeta` + `filter_kwargs = {}` on `BaseGenericAPIView`; no standalone queryset utils; no `http_method_names`. Serializers never import ViewMeta querysets; resolve models themselves. `utils/db.py` = mutations only (counts/inc/dec/cancel). Representation uses prefetched `to_attr`; no per-object related queries.

**Serializer and Route Ownership (2026-08-10)** — Serializer `create()`/`update()` own persistence. Views pass context to `serializer.save(...)`; must not capture return, assign `serializer.instance`, or reload for write-response. Route getters take no id args; resolve `self.kwargs["pk"]` via `get_object_or_404`. Shared `*ViewMeta` only if `pk` same resource type. Canonical `<uuid:pk>`. Service docs delete via `/programs/program-result-documents/<uuid:pk>/`; parent result from resolved document. Create response needing nested prefetch: reload via ViewMeta queryset → `serializer.instance`.
