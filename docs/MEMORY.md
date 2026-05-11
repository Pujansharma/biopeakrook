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

---

## Conventions Established Through Collaboration

**Naming Standards (2026-05-11)**
- **NO abbreviations** in code: variables, parameters, loop variables, annotations
- Use explicit, brief, and formal names
- Examples: `count` not `cnt`, `assignment` not `asg`, `service` not `s`
- Added to CODING_RULES.md Section 1 with examples
- Why: Readability, consistency, prevents ambiguity (especially in subquery annotations)