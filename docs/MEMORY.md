# Biopeak Nexus — Project Memory

---

## User Preferences

- Never revert/alter code user manually edited. User changes something back = final state — don't touch those lines again unless explicitly asked.
- Never create Django migration files manually, never run `makemigrations`. User handles all migration generation.
- Always use `<uuid:pk>/` for UUID detail URL path parameters.
- No function return/output type annotations unless user explicitly requests.
- Prefer explicit `BaseModelSerializer` contract with `Meta.model` + declared fields over overriding `to_representation()` to delegate to another serializer.
- Keep related-object response fields nested; don't duplicate their attributes as flattened top-level fields.
- Don't repeat explicitly declared `read_only=True` serializer fields in `Meta.read_only_fields`.

---

## Architecture Decisions

| Decision | Reason |
|---|---|
| On-demand slot generation (no pre-stored slots) | Avoids DB bloat; computed at query time via `appointments/utils/intervals.py` |
| UUID7 primary keys on all models | Better DB performance + sortable by time |
| Center-scoped data isolation via `X-Center-ID` header | Multi-tenant design requirement |
| `uv` as sole package manager | Faster, reproducible, replaces pip entirely |
| All docs in `docs/` folder | Enforced by `CODING_RULES.md` |
| Pre-consultation schema 3.0.0 (2026-06-30) | Normalized 15-table session-scoped model: `PreConsultationCategorySelection`, `PreConsultationConcern` (+ symptom/source/family/probe children), `PreConsultationMedicalHistory` (+ diagnosis/allergy/surgery/medication/sexual-health children), `PreConsultationLifestyleAnswer`, `PreConsultationHealthGoal`. Session fields: `directive_schema_id`, `current_layer`. Directive taxonomy: category/concern/symptom/concern_source/age_band. Layer ids renamed (`patient_category`, `patient_concern`, `patient_symptom`, `patient_concern_probe`). Cascade reset on layer edit via `layers/reset.py`. Squashed to `0001_initial`. |
| Pre-consultation response envelope (2026-06-30) | `success` only at top level; never inside `data`. `pre_consultation_response()` strips stray `success` from `data`. |
| Program/service/provider/composite ERD direction (2026-06-11) | User confirmed ERD reflects newer biz requirements, keep domain name `Client` not implementation naming. `Service` extended w/ type + products. Composite models not yet defined, create from ERD. Service defs stay reusable, center availability uses `CenterServiceAssignment`, assigned quantities live on `ProgramService`, assessment behavior comes from provider/product callbacks. |
| Shared program-service allocation (2026-07-27) | Ordinary + composite programs use `ProgramService` as common assigned service line. Preserve established fields `sessions_count`, `sessions_used`, `sessions_cancelled` on `ProgramService`; don't rename or add model properties/aliases. `sessions_count=0` = unlimited sessions, must stay valid, no positive-count check constraint. `TherapyProgramService` retains therapy-only runtime data like `redeem_code`, `RedemptionHistory` still points to it. Cancellation history created only when parent `Program.program_type` is `THERAPY`, not for composite programs. Composite list/create uses one `CompositeProgramSerializer`; `CompositeProgramSerializer.create()` returns newly created `CompositeProgram` directly, no rebuild through composite-program queryset. Serializer object checks belong in `create()`/`update()`, `SerializerMethodField` handlers need no return annotations. User generates + reviews migrations. |
| Composite service prerequisites (2026-07-29) | `CompositeServicePrerequisite` singleton config attached to `CompositeTemplateService`. Retains `BaseModel`, permits empty `related_services` M2M, defaults to `require_any`, stores ORM-subquery-maintained `related_services_count`. Composite-template-service responses include prerequisite metadata + three-service `related_services` preview. Updates use `PUT programs/composites/services/<template_service_uuid>/prerequisites/`; complete linked + annotated available-service lists use paginated `prerequisites/<template_service_uuid>/prerequisite-services/` and `available-prerequisite-services/` GET endpoints. |
| Composite program service counters (2026-08-05) | `CompositeProgram` stores ORM-subquery-maintained add-on + service-category counts. Category counts include both template services + add-ons; `add_ons_count` overlaps category counters. Parent `Program.services_count` remains authoritative total, all counts include inactive/cancelled assigned services. |
| Program UID integration (2026-08-05) | All active therapy + composite `Program` creation paths generate shared `P`-prefixed, four-digit-minimum sequence UID inside their atomic transaction. Program API representations expose `uid` read-only. Nullable field has no DB uniqueness constraint. `backfill_program_uids` assigns + saves UIDs for null rows one at a time; command not yet executed by Codex. |
| Program subtype/service subtype split (2026-06-12) | `ProgramService` is common assigned service line. `TherapyProgram.program` is primary key, `TherapyProgramService.program_service` is primary key. Therapy-only session/redemption fields live on `TherapyProgramService`, `RedemptionHistory` points to `TherapyProgramService`. `wellness_*` names are compatibility properties/API aliases only. User will discard old data + generate fresh migrations manually; don't create migration files for this change. |
| Test kit inventory + assignment merge (2026-08-06) | `test_kit_inventory` app absorbs `product_inventory` + `test_kit_assignment`. Legacy tables dropped in `test_kit_inventory/0002_remove_legacy_inventory_and_assignment_tables` (RunSQL + cleans `django_migrations`). Old apps removed from repo. APIs: `/test_kit_inventory/` (specs, consignment, all, batches, customer, assign, assignment-history, providers/add, products/add). Inventory-native `Provider`/`Product`/`Batch`/`Item`/`Assignment` — no catalog `tags.type` filter. Postman repo: `docs/postman/collections/test-kit-inventory.postman_collection.json`. Postman cloud: `Biopeak-Nexus` collection uid `56091494-351b66f2-736b-4338-b684-ee520aa19e94` — folder `test_kit_inventory`. |
| Product `is_assignable` (2026-08-06) | `test_kit_inventory.Product.is_assignable` default `False`. All products inventory; only `is_assignable=True` for kit assignment. Specs: `GET /test_kit_inventory/specs/?is_assignable=0|1` filters providers/products. Specs product payload includes `is_assignable`. Product create accepts optional `is_assignable`. Assign `POST .../assign/` rejects non-assignable products. |
| Test kit assignment (2026-07-30) | ~~`test_kit_assignment` app~~ merged into `test_kit_inventory` (2026-08-06). One active kit per `CustomerProfile`; assignee always profile id. Eligible = completed pre-consult + no active assignment. Global APIs (no `X-Center-ID`). Spec: `docs/superpowers/specs/2026-07-30-test-kit-assignment-design.md`. |
| Product inventory QC acks (2026-08-04) | `qc_ack_packaging` / `qc_ack_all_components` write gate + persisted on `test_kit_inventory.Item`. |
| Lead/profile onboarding flags (2026-08-06) | `Lead.is_onboarding_completed` dropped. Completion only on `CustomerProfile.is_onboarding_completed`. Both `Lead` + `CustomerProfile` `is_onboarding_sent` default `False`. Lead POST/PATCH writable: `is_onboarding_sent`. Center create + profile PATCH: writable `is_onboarding_sent`; `is_onboarding_completed` read-only on center home/detail responses. Login shell profile copies `lead.is_onboarding_sent`. Lead PATCH flipping `is_onboarding_sent` syncs linked profile. `is_invited` independent (filter/API), no longer drives profile sent. Ready for session: lead `sent=True` and (no profile or profile not completed). |
| Diagnostics orders / Orange Labs (2026-08-11) | New app `diagnostics_orders`. Local catalog (`CatalogItem` + `CatalogCityPrice` w/ city price + `tat_in_hours`). Cities: BLR/DEL/NOA/HYD/MUM/GGN/PNQ via pincode ranges in `utils/constants.py`. Orders multi-patient; token never in FE response. SDK: `integrations/orange_labs/sdk.py`. Webhook: `webhooks/orange_labs/`. RBAC feature `diagnostics_orders`. Env: `*_ORANGE_LABS_API_BASE_URL` / `*_ORANGE_LABS_API_KEY`. Postman local: `docs/postman/collections/diagnostics-orders.postman_collection.json`. Cloud Biopeak-Nexus folder `diagnostics_orders` (flat requests incl. `POST add-test-package/`; admin+associate share same APIs via `{{access_token}}` + optional `X-Center-ID`). `POST /add-test-package/` create-only catalog seed (`category` + `is_custom_package`; optional `city_prices`; duplicate `diagnostic_test_id` → 400). User generates migrations. |
| Diagnostics `order_link` (2026-08-11) | ~~Dropped~~ `order_link` + `raw_create_request` removed from `DiagnosticOrder`. Keep `raw_create_response`. Create/detail APIs no longer expose `order_link`. User generates migration. |
| Orange create payload shape (2026-08-11) | Create-order body: plain address; gender via `Gender.MAPPING` on profile (`Male`/`Female`/`Other`); `age` + `test_id`/`package_id` as strings per Orange OpenAPI. Serviceability query encoding unchanged. |

---

## Known Issues / In-Progress Work

**Implemented:** CenterServiceAssignment Bridged Model (2026-05-11)
- ✅ Replace Service.centers M2M w/ explicit bridged model for per-center activation control
- ✅ Updated: services/, external/ (views, serializers, utilities, admin)
- ✅ Task doc: `docs/tasks/center-services-bridge-model.md`
- Pending: Migration creation + execution

**Implemented:** External Centers Count Tracking (2026-05-11)
- ✅ Added `external_centers_count` to CustomerProfile (tracks non-primary center links)
- ✅ Increment/decrement functions in `accounts/customers/utils/db.py`
- ✅ Serializer updated to call count updates on add/remove
- ✅ Management command: `python manage.py recompute_external_centers_count`

**COMPLETED:** Email/Phone Field Separation (2026-05-12)
- ✅ Models: `contact_phone` on Admin/Associate, `contact_email` on Customer
- ✅ Serializers: Updated to expose contact_phone (not user.phone) for staff, contact_email for customers
- ✅ All create/update methods enforce field separation:
  - Admin/Associate creation: phone=None, user.email set
  - Customer creation: email=None, user.phone set
- ✅ Explicit validation functions: check_admin_associate_user_exists(), check_customer_user_exists()
- ✅ All update methods pop unwanted fields (user.phone for staff, user.email for customers)
- ✅ Django admin updated:
  - AdminUserAdmin: contact_phone in list_display, search_fields, fieldsets
  - AssociateAdmin: contact_phone in list_display, search_fields, organized fieldsets
  - CustomerAdmin: contact_email in list_display, search_fields, fieldsets
  - CustomerProfileAdmin: contact_email in list_display, better fieldsets organization
- **Files modified:**
  - accounts/admins/serializers.py: phone→contact_phone in serializers, prevent phone in updates
  - accounts/associates/serializers.py: phone→contact_phone in 4 serializers, fix CenterAssociateSerializer data flow
  - accounts/admins/utils/db.py: explicit phone=None in create_admin_user()
  - accounts/utils/db.py: new explicit validation functions for account types
  - accounts/admins/admin.py: contact_phone in display, search, and fieldsets
  - accounts/associates/admin.py: contact_phone in display, search, and fieldsets
  - accounts/customers/admin.py: contact_email in display, search, and fieldsets
- **Changes:** ~150 insertions/80 deletions across 7 files, all syntax validated

---

## Tooling Notes

**django-debug-toolbar v7 (2026-06-20)**
- `include("debug_toolbar.urls")` still works in v7 — no URL config change needed upgrading from v6
- `CompressedManifestStaticFilesStorage` (used in development.py) requires `collectstatic` run first; without it, toolbar static files stale/missing, causing `Uncaught TypeError: Cannot read properties of null (reading 'dataset')` in toolbar.js
- Fix: run `uv run manage.py collectstatic` after upgrading package

---

## Conventions Established Through Collaboration

**Naming Standards (2026-05-11)**
- **NO abbreviations** in code: variables, parameters, loop variables, annotations
- Use explicit, brief, formal names
- Examples: `count` not `cnt`, `assignment` not `asg`, `service` not `s`
- Added to CODING_RULES.md Section 1 w/ examples
- Why: Readability, consistency, prevents ambiguity (especially in subquery annotations)

**Django FK Access (2026-05-18)**
- **NEVER use `<field>_id`** (e.g. `program_service.program_id`)
- **ALWAYS use `.pk`** via relation (e.g. `program_service.program.pk`)
- Added to CODING_RULES.md Section 11
- Why: Explicit, consistent, avoids implicit Django column accessor confusion

**ORM Single-Object Lookups (2026-07-27)**
- Use `filter(...).first()` for serializer + utility object lookups.
- Don't introduce direct `.get()` lookups; explicitly handle missing result where required.

**Serializer Add/Remove Actions (2026-08-04)**
- Keep `add_*`/`remove_*` relation handling simple: accept write-only `{id}` lists, pop each list from `validated_data` w/ empty-list fallback, delegate each op to small action helper.
- Each action helper returns immediately for empty input, validates supplied IDs against allowed parent scope w/ one ORM query + set difference, raises error on its own serializer field, then calls related manager's bulk `add()`/`remove()` w/ validated IDs.
- Keep `create()`/`update()` as transaction-level orchestration: save main instance, run remove before add so add wins for IDs present in both inputs, update maintained counts, refresh only required fields, rebuild any response preview, return instance.
- Avoid duplicating relation-ID normalization/validation in `create()`/`update()`; don't add prevalidation structures when action helpers can perform complete operation directly.

**View Querysets (2026-07-27)**
- Keep reusable endpoint queryset construction in `*ViewMeta` mixin derived from `BaseGenericAPIView`.
- Concrete views subclass mixin, call queryset method through `self`, following `CenterViewMeta`; don't create standalone queryset utility functions for this pattern.
- Use established `filter_kwargs = {}` pattern for request/user-specific queryset scoping; don't introduce custom permission-queryset mixins.
- Don't add `http_method_names`; rely on project's established base view classes.
- Keep strict serializer/view queryset boundary: serializers never import/reuse queryset builders from views or `*ViewMeta` classes. Serializers resolve own required models directly through model managers.
- Serializer imports from `utils/db.py` limited to state-changing utilities like count refreshes, increments, decrements, cancellations, related mutation helpers; object/queryset resolution belongs directly in serializer, optimized response querysets belong exclusively in `*ViewMeta`.
- Serializer representation methods must consume prefetched `to_attr` data supplied by view queryset, must not query related models/managers per serialized object. Create views needing optimized nested response should reload saved instance through own `*ViewMeta` queryset, assign to `serializer.instance`.