# Biopeak Nexus — Project Memory

This file is the persistent memory store for Claude Code sessions on this project.

**Rules:**
- Claude reads this file at the start of every relevant session.
- Entries are added here for decisions, patterns, and context that are not derivable from reading the code.
- Entries must include a date. Stale entries should be removed or updated.
- Do NOT record things that can be determined by reading the current codebase, git log, or other docs.

---

## User Preferences

_(Add entries here as preferences are established)_

---

## Architecture Decisions

| Date | Decision | Reason |
|---|---|---|
| Apr 2026 | On-demand slot generation (no pre-stored slots) | Avoids DB bloat; computed at query time via `appointments/utils/intervals.py` |
| Apr 2026 | UUID7 primary keys on all models | Better DB performance + sortable by time |
| Apr 2026 | Center-scoped data isolation via `X-Center-ID` header | Multi-tenant design requirement |
| Apr 2026 | `uv` as the sole package manager | Faster, reproducible, replaces pip entirely |
| Apr 2026 | All docs in `docs/` folder | Enforced by `CODING_RULES.md` |

---

## Known Issues / In-Progress Work

_(Add entries as issues are identified or work begins)_

---

## Conventions Established Through Collaboration

_(Add entries when non-obvious patterns are confirmed or corrected during sessions)_

---

*This file is maintained by Claude Code. Last updated: April 2026.*