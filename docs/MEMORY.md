# Biopeak Nexus — Project Memory

---

## User Preferences

- Never revert/alter code user manually edited. User change back = final. Don't touch those lines unless asked.
- Never create Django migration files manually, never run `makemigrations`. User owns migrations.
- Always use `<uuid:pk>/` for UUID detail URL path params.
- No function return/output type annotations unless user asks.
- Prefer explicit `BaseModelSerializer` + `Meta.model` + declared fields over `to_representation()` delegating to another serializer.
- Keep related-object fields nested; don't flatten to top level.
- Don't repeat explicit `read_only=True` fields in `Meta.read_only_fields`.
- "update postman collection" → sync Postman cloud `Biopeak-Nexus` uid `56091494-351b66f2-736b-4338-b684-ee520aa19e94` via `POSTMAN_API_KEY`, not only local `docs/postman/` JSON.

---

## Architecture Decisions

| Decision | Reason |
|---|---|
| On-demand slot generation (no pre-stored slots) | No DB bloat; `appointments/utils/intervals.py` at query time |
| UUID7 PKs all models | Better DB perf + time-sortable |
| Center isolation via `X-Center-ID` | Multi-tenant |
| `uv` sole package manager | Faster, reproducible; replaces pip |
| All docs in `docs/` | `CODING_RULES.md` |
| Pre-consultation schema 3.0.0 (2026-06-30) | Normalized 15-table session-scoped model: `PreConsultationCategorySelection`, `PreConsultationConcern` (+ symptom/source/family/probe), `PreConsultationMedicalHistory` (+ diagnosis/allergy/surgery/medication/sexual-health), `PreConsultationLifestyleAnswer`, `PreConsultationHealthGoal`. Session: `directive_schema_id`, `current_layer`. Taxonomy: category/concern/symptom/concern_source/age_band. Layer ids: `patient_category`, `patient_concern`, `patient_symptom`, `patient_concern_probe`. Cascade reset `layers/reset.py`. Squashed `0001_initial`. |
| Pre-consultation envelope (2026-06-30) | `success` top-level only; never in `data`. `pre_consultation_response()` strips stray `success`. |
| Program ERD direction (2026-06-11) | Keep domain `Client`. `Service` + type/products. Composites from ERD. Reusable services; center via `CenterServiceAssignment`; qty on `ProgramService`; assessment via provider/product callbacks. |
| ProgramService shared + therapy split (2026-06-12 / 2026-07-27) | Ordinary + composite use `ProgramService` line: keep `sessions_count`/`sessions_used`/`sessions_cancelled`; no rename/aliases; `sessions_count=0` = unlimited (no positive check). `TherapyProgram.program` PK; `TherapyProgramService.program_service` PK; therapy runtime (`redeem_code`) + `RedemptionHistory` → `TherapyProgramService`. Cancel/`RedemptionHistory` only if `Program.program_type` is `THERAPY`. `wellness_*` = API aliases only. One `CompositeProgramSerializer`; `create()` returns `CompositeProgram` direct. Object checks in `create()`/`update()`; no return annotations on `SerializerMethodField`. User owns migrations. |
| Composite prerequisites (2026-07-29) | `CompositeServicePrerequisite` singleton on `CompositeTemplateService`. `BaseModel`; empty `related_services` OK; default `require_any`; ORM `related_services_count`. Responses: prerequisite meta + 3-service preview. `PUT programs/composites/services/<template_service_uuid>/prerequisites/`; paginated `prerequisites/<uuid>/prerequisite-services/` + `available-prerequisite-services/`. |
| Composite program counters (2026-08-05) | ORM add-on + category counts on `CompositeProgram`. Category = template + add-ons; `add_ons_count` overlaps categories. Parent `Program.services_count` authoritative; counts include inactive/cancelled. |
| Program UID (2026-08-05) | Active therapy + composite creates: `P`-prefix, ≥4-digit sequence UID in same txn. API `uid` read-only. Nullable; no DB unique. `backfill_program_uids` one-row-at-a-time; not run yet. |
| Test kit inventory merge (2026-08-06) | `test_kit_inventory` absorbs `product_inventory` + `test_kit_assignment`. Legacy drop `0002_remove_legacy_inventory_and_assignment_tables`. APIs `/test_kit_inventory/` (specs, consignment, all, batches, customer, assign, assignment-history, providers/add, products/add). Native `Provider`/`Product`/`Batch`/`Item`/`Assignment` — no `tags.type` filter. One active kit/`CustomerProfile`; assignee = profile id. Eligible = completed pre-consult + no active kit. Global APIs (no `X-Center-ID`). Spec: `docs/superpowers/specs/2026-07-30-test-kit-assignment-design.md`. Postman local `docs/postman/collections/test-kit-inventory.postman_collection.json`; cloud folder `test_kit_inventory`. |
| Product `is_assignable` (2026-08-06) | Default `False`. Only `True` assignable. Specs `?is_assignable=0\|1`; payload + create optional; assign rejects non-assignable. |
| Product QC acks (2026-08-04) | `qc_ack_packaging` / `qc_ack_all_components` gate + persist on `Item`. |
| Lead/profile onboarding (2026-08-06) | Drop `Lead.is_onboarding_completed`. Completion only `CustomerProfile.is_onboarding_completed`. Both `is_onboarding_sent` default `False`. Lead POST/PATCH + center create/profile PATCH writable `is_onboarding_sent`; `is_onboarding_completed` read-only on center home/detail. Login shell copies `lead.is_onboarding_sent`. Lead PATCH syncs linked profile. `is_invited` independent. Ready: lead `sent=True` and (no profile or profile incomplete). |
| Diagnostics / Orange Labs (2026-08-11+) | App `diagnostics_orders`. Catalog `CatalogItem` + `CatalogCityPrice` (`price`, `tat_in_hours`). Cities BLR/DEL/NOA/HYD/MUM/GGN/PNQ via `utils/constants.py` pincode ranges. Multi-patient; token never in FE. SDK `integrations/orange_labs/sdk.py`. Webhook `webhooks/orange_labs/`. RBAC `diagnostics_orders`. Env `*_ORANGE_LABS_API_BASE_URL` / `*_ORANGE_LABS_API_KEY` / `*_ORANGE_LABS_WEBHOOK_SECRET`. `POST /add-test-package/` create-only (`category`, `is_custom_package`; optional `city_prices`; dup `diagnostic_test_id` → 400). Dropped `order_link` + `raw_create_request`; keep `raw_create_response`. Create: plain address; gender `Gender.MAPPING` (`Male`/`Female`/`Other`); `age` + `test_id`/`package_id` strings. Webhook `POST /webhooks/orange-labs/`: HMAC `X-OH-Signature` (raw body, SHA256 hex) + secret; idempotency `X-OH-Event-Id`; lookup `payload.request.city_request_id` (fallback `payload.order.city_request_id`); status = top-level `event`. On `test.completed_sent` / `order.completed` merge slim reports by `id` (`file_type`, `file_name`, `tokenize_public_file_url`). `DiagnosticOrderRescheduleHistory` after Orange reschedule; denorm `last_reschedule_*` + `total_rescheduled`; nested `reschedule_history` on `GET .../order/<request_id>/` only. Postman local `docs/postman/collections/diagnostics-orders.postman_collection.json`; cloud folder `diagnostics_orders` (admin+associate same APIs, `{{access_token}}` + optional `X-Center-ID`). User owns migrations. |
| Leads API v2 (2026-08-10) | Admin writes `/leads/v2/` (POST create+shell, PATCH update+shell sync). v1 GET/POST/PATCH → 400; v1 DELETE still `/leads/{id}/`. Bypass login `/auth/login-phone-direct/` = User lookup only, no shell. No legacy backfill. Postman local `docs/postman/collections/leads.postman_collection.json`; cloud folder `leads`. |
| Emergency contact dropped (2026-08-07) | Removed `CustomerProfile.emergency_contact_name` / `emergency_contact_phone`. Pre-consult baseline no longer R/W those. |

---

## Known Issues / In-Progress Work

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

**View querysets (2026-07-27)** — `*ViewMeta` + `filter_kwargs = {}` on `BaseGenericAPIView`; no standalone queryset utils; no `http_method_names`. Serializers never import ViewMeta querysets; resolve models themselves. `utils/db.py` = mutations only (counts/inc/dec/cancel). Representation uses prefetched `to_attr`; no per-object related queries. Create response: reload via ViewMeta queryset → `serializer.instance`.
