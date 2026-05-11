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

**Planned:** CenterServiceAssignment Bridged Model (2026-05-11)
- Replace Service.centers M2M with explicit bridged model for per-center activation control
- Enables granular service availability without losing relationships
- Task doc: `docs/tasks/center-services-bridge-model.md`
- Affects: views.py, serializers.py, utils/db.py, admin.py
- Will require data migration to move existing M2M relationships

---

## Conventions Established Through Collaboration

_(Add entries when non-obvious patterns are confirmed or corrected during sessions)_