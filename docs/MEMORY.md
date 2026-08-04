# Biopeak Nexus — Project Memory

---

## User Preferences

- Never revert or alter code the user has manually edited. If the user changes something back, that is the final state — do not touch those lines again unless explicitly asked.
- Never create Django migration files manually and never run `makemigrations`. The user handles all migration generation.
- Always use `<uuid:pk>/` for UUID detail URL path parameters.
- Do not add function return/output type annotations unless the user explicitly requests them.
- Prefer an explicit `BaseModelSerializer` contract with `Meta.model` and declared fields over overriding `to_representation()` to delegate to another serializer.
- Keep related-object response fields nested; do not duplicate their attributes as flattened top-level fields.
- Do not repeat explicitly declared `read_only=True` serializer fields in `Meta.read_only_fields`.

---

## Architecture Decisions

| Decision | Reason |
|---|---|
| On-demand slot generation (no pre-stored slots) | Avoids DB bloat; computed at query time via `appointments/utils/intervals.py` |
| UUID7 primary keys on all models | Better DB performance + sortable by time |
| Center-scoped data isolation via `X-Center-ID` header | Multi-tenant design requirement |
| `uv` as the sole package manager | Faster, reproducible, replaces pip entirely |
| All docs in `docs/` folder | Enforced by `CODING_RULES.md` |
| Pre-consultation schema 3.0.0 (2026-06-30) | Normalized 15-table session-scoped model: `PreConsultationCategorySelection`, `PreConsultationConcern` (+ symptom/source/family/probe children), `PreConsultationMedicalHistory` (+ diagnosis/allergy/surgery/medication/sexual-health children), `PreConsultationLifestyleAnswer`, `PreConsultationHealthGoal`. Session fields: `directive_schema_id`, `current_layer`. Directive taxonomy: category/concern/symptom/concern_source/age_band. Layer ids renamed (`patient_category`, `patient_concern`, `patient_symptom`, `patient_concern_probe`). Cascade reset on layer edit via `layers/reset.py`. Squashed to `0001_initial`. |
| Pre-consultation response envelope (2026-06-30) | `success` only at top level; never inside `data`. `pre_consultation_response()` strips stray `success` from `data`. |
| Program/service/provider/composite ERD direction (2026-06-11) | User confirmed the ERD reflects newer business requirements and should keep the domain name `Client` rather than implementation naming. `Service` will be extended with type and products. Composite models are not yet defined and should be created from the ERD. Service definitions stay reusable, center availability uses `CenterServiceAssignment`, assigned quantities live on `ProgramService`, and assessment behavior comes from provider/product callbacks. |
| Shared program-service allocation (2026-07-27) | Ordinary and composite programs use `ProgramService` as the common assigned service line. Preserve the established fields `sessions_count`, `sessions_used`, and `sessions_cancelled` on `ProgramService`; do not rename them or add model properties/aliases. `sessions_count=0` means unlimited sessions, so it must remain valid and must not have a positive-count check constraint. `TherapyProgramService` retains therapy-only runtime data such as `redeem_code`, while `RedemptionHistory` continues to point to it. Cancellation history is created only when the parent `Program.program_type` is `THERAPY`, not for composite programs. Composite list/create uses one `CompositeProgramSerializer`; `CompositeProgramSerializer.create()` returns the newly created `CompositeProgram` directly without rebuilding it through the composite-program queryset. Serializer object checks belong in `create()`/`update()`, and `SerializerMethodField` handlers do not need return annotations. The user generates and reviews migrations. |
| Composite service prerequisites (2026-07-29) | `CompositeServicePrerequisite` is a singleton configuration attached to `CompositeTemplateService`. It retains `BaseModel`, permits an empty `related_services` M2M, defaults to `require_any`, and stores an ORM-subquery-maintained `related_services_count`. Composite-template-service responses include prerequisite metadata and a three-service `related_services` preview. Updates use `PUT programs/composites/services/<template_service_uuid>/prerequisites/`; complete linked and annotated available-service lists use the paginated `prerequisites/<template_service_uuid>/prerequisite-services/` and `available-prerequisite-services/` GET endpoints. |

---

## Known Issues / In-Progress Work

**Implemented:** CenterServiceAssignment Bridged Model (2026-05-11)
- ✅ Replace Service.centers M2M with explicit bridged model for per-center activation control
- ✅ Updated: services/, external/ (views, serializers, utilities, admin)
- ✅ Task doc: `docs/tasks/center-services-bridge-model.md`
- Pending: Migration creation and execution

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
- `include("debug_toolbar.urls")` still works in v7 — no URL config change needed when upgrading from v6
- `CompressedManifestStaticFilesStorage` (used in development.py) requires `collectstatic` to have been run; without it, toolbar static files are stale/missing, causing `Uncaught TypeError: Cannot read properties of null (reading 'dataset')` in toolbar.js
- Fix: run `uv run manage.py collectstatic` after upgrading the package

---

## Conventions Established Through Collaboration

**Naming Standards (2026-05-11)**
- **NO abbreviations** in code: variables, parameters, loop variables, annotations
- Use explicit, brief, and formal names
- Examples: `count` not `cnt`, `assignment` not `asg`, `service` not `s`
- Added to CODING_RULES.md Section 1 with examples
- Why: Readability, consistency, prevents ambiguity (especially in subquery annotations)

**Django FK Access (2026-05-18)**
- **NEVER use `<field>_id`** (e.g. `program_service.program_id`)
- **ALWAYS use `.pk`** via the relation (e.g. `program_service.program.pk`)
- Added to CODING_RULES.md Section 11
- Why: Explicit, consistent, avoids implicit Django column accessor confusion

**ORM Single-Object Lookups (2026-07-27)**
- Use `filter(...).first()` for serializer and utility object lookups.
- Do not introduce direct `.get()` lookups; explicitly handle a missing result where required.

**Serializer Add/Remove Actions (2026-08-04)**
- Keep `add_*` and `remove_*` relation handling simple: accept write-only `{id}` lists, pop each list from `validated_data` with an empty-list fallback, and delegate each operation to a small action helper.
- Each action helper should return immediately for empty input, validate the supplied IDs against the allowed parent scope with one ORM query and a set difference, raise an error on its own serializer field, then call the related manager's bulk `add()` or `remove()` with the validated IDs.
- Keep `create()` and `update()` as transaction-level orchestration: save the main instance, run remove before add so add wins for IDs present in both inputs, update maintained counts, refresh only the required fields, rebuild any response preview, and return the instance.
- Avoid duplicating relation-ID normalization and validation in `create()` and `update()`, and do not add prevalidation structures when the action helpers can perform the complete operation directly.

**View Querysets (2026-07-27)**
- Keep reusable endpoint queryset construction in a `*ViewMeta` mixin derived from `BaseGenericAPIView`.
- Concrete views should subclass the mixin and call the queryset method through `self`, following `CenterViewMeta`; do not create standalone queryset utility functions for this pattern.
- Use the established `filter_kwargs = {}` pattern for request/user-specific queryset scoping; do not introduce custom permission-queryset mixins.
- Do not add `http_method_names`; rely on the project’s established base view classes.
