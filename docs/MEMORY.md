# Biopeak Nexus — Project Memory

---

## User Preferences

- Never revert or alter code the user has manually edited. If the user changes something back, that is the final state — do not touch those lines again unless explicitly asked.

---

## Architecture Decisions

| Decision | Reason |
|---|---|
| On-demand slot generation (no pre-stored slots) | Avoids DB bloat; computed at query time via `appointments/utils/intervals.py` |
| UUID7 primary keys on all models | Better DB performance + sortable by time |
| Center-scoped data isolation via `X-Center-ID` header | Multi-tenant design requirement |
| `uv` as the sole package manager | Faster, reproducible, replaces pip entirely |
| All docs in `docs/` folder | Enforced by `CODING_RULES.md` |
| Program/service/provider/composite ERD direction (2026-06-11) | User confirmed the ERD reflects newer business requirements and should keep the domain name `Client` rather than implementation naming. `Service` will be extended with type and products. Composite models are not yet defined and should be created from the ERD. Service definitions stay reusable, center availability uses `CenterServiceAssignment`, assigned quantities live on `ProgramService`, and assessment behavior comes from provider/product callbacks. |
| Program subtype/service subtype split (2026-06-12) | `ProgramService` is the common assigned service line. `TherapyProgram.program` is the primary key, and `TherapyProgramService.program_service` is the primary key. Therapy-only session/redemption fields live on `TherapyProgramService`, and `RedemptionHistory` points to `TherapyProgramService`. `wellness_*` names are compatibility properties/API aliases only. User will discard old data and generate fresh migrations manually; do not create migration files for this change. |

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
