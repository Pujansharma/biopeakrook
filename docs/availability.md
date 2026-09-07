# Availability System

This document explains how **availability** works in Biopeak Nexus — what it means, which resources it applies to, how to read calendars, and how to manage schedules through the API.

No prior backend knowledge required.

---

## What is availability?

**Availability** answers: *“When is this resource free to be booked?”*

Resources include:

| Resource | Base schedule comes from | Subtractors (things that remove time) |
|---|---|---|
| **Center** | Weekly operating hours (`CenterOperatingHour`) | Closures (`CenterClosure`) |
| **Associate** (at a center) | Center hours **∩** weekly roster | Blocks, leaves, closures |
| **Room** | Center hours (rooms inherit center hours) | Blocks, downtimes, closures |
| **Equipment** | Center hours (equipment inherits center hours) | Blocks, downtimes, closures |

Nothing is pre-stored as bookable slots. The API **computes** free windows on demand using interval math:

```
available = base_windows − blocks − leaves/downtimes − closures
```

Collectors load only rows that can affect the requested `start`/`granularity` window (one-offs by date/datetime overlap; recurring by `effective_from` / `effective_until`). Response shape unchanged.

All datetimes are stored in **UTC** but day boundaries use the project timezone (`Asia/Kolkata` until centers get their own timezone field).

---

## Calendar APIs (read)

One GET endpoint per resource type. All return the same day-by-day shape.

### Query parameters

| Param | Default | Values |
|---|---|---|
| `start` | today | ISO date `YYYY-MM-DD` — anchor date for the range |
| `granularity` | `day` (most resources); **`week` for center calendar** | `day`, `week`, or `month` |

- **day** — single day (`start`)
- **week** — Monday–Sunday week containing `start`
- **month** — full calendar month containing `start`

`GET /centers/<center_id>/availability/` defaults to **week** when `granularity` is omitted. Associate, room, and equipment calendars still default to **day**. No cross-center aggregate associate calendar.

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/centers/<center_id>/availability/` | Center hours + closures |
| GET | `/centers/<center_id>/availability/associates/<associate_id>/` | Associate at one center |
| GET | `/centers/<center_id>/availability/rooms/<room_id>/` | Room at center |
| GET | `/centers/<center_id>/availability/equipment/<equipment_id>/` | Equipment at center |

### Authentication

- **JWT Bearer** required (`Authorization: Bearer <token>`)
- **Center-scoped routes**: admin or associate with a valid assignment; associates must send `X-Center-ID` matching the URL center
- Associate calendar/roster/block/leave routes require the target associate to have an **active center assignment** at the URL center

### Response envelope

```json
{
  "detail": "Center availability retrieved.",
  "data": { ... }
}
```

### Example: center calendar (one day)

```json
{
  "resource_type": "center",
  "center_id": "0195a1b2-...",
  "timezone": "Asia/Kolkata",
  "start": "2026-08-26",
  "end": "2026-08-26",
  "granularity": "day",
  "days": [
    {
      "date": "2026-08-26",
      "day_of_week": "2",
      "day_of_week_name": "Wednesday",
      "base_windows": [
        {
          "start": "2026-08-26T03:30:00+00:00",
          "end": "2026-08-26T12:30:00+00:00"
        }
      ],
      "available_windows": [],
      "events": [
        {
          "type": "closure",
          "id": "0195a1b2-...",
          "start": "2026-08-25T18:30:00+00:00",
          "end": "2026-08-26T18:29:59+00:00",
          "closure_type": "holiday",
          "reason": "Independence Day"
        }
      ]
    }
  ]
}
```

**Field meanings per day:**

- `day_of_week` — `AppointmentDays` code (`"0"`=Monday … `"6"`=Sunday)
- `day_of_week_name` — display label (`Monday` … `Sunday`)
- `base_windows` — recurring schedule expanded to concrete UTC intervals (before subtractors)
- `available_windows` — `base_windows` after all subtractors
- `events` — raw items that reduce availability (blocks, leaves, downtimes, closures) with a `type` label

### Example: associate at center

Same shape, plus `associate_id`. Base windows = center hours intersected with the associate’s **roster** entries for that center.

Event types you may see:

- `associate_block` / `associate_block_recurring`
- `associate_leave` (includes `scope`: `center` or `all_centers`)
- `closure`

---

## Write APIs (manage schedules)

All write routes are **center-scoped** under `/centers/<center_id>/availability/`.

| Action | Method | Notes |
|---|---|---|
| Create | POST | Returns created record |
| Update | PATCH | Soft-deactivate with `"is_active": false` |
| Delete | — | **Not supported** — use PATCH |

List endpoints exist on each collection URL (GET) with optional `?active=0|1`.

### Permissions (v1)

`IsAuthenticated` + (`IsAdminUser` **OR** `IsAssociateUser` with valid center assignment).

Associates: `X-Center-ID` must match URL center (same rule as centers v2).

### Center operating hours (weekly)

**GET/PATCH** `/centers/<center_id>/availability/operating-hours/`

Bulk upsert the same open/close window across selected weekdays; mark other days closed.

```json
{
  "open_time": "09:00:00",
  "close_time": "18:00:00",
  "days": ["0", "1", "2", "3", "4", "5"],
  "closed_days": ["6"]
}
```

- `days` — open days (`0`=Monday … `6`=Sunday); share `open_time` / `close_time`; `is_open=true`
- `closed_days` — closed days; `is_open=false`, times null
- Idempotent upsert per `(center, day_of_week)`
- `open_time` / `close_time` required when `days` is non-empty; must have `open_time < close_time`
- Days omitted from both lists are left unchanged
- GET lists rows; optional `?active=0|1` (default active only)
- **Roster guard:** PATCH rejects if any **active** associate roster would fall outside the new window, or if a day being closed still has active roster. 400 `detail.day_errors` (codes below). Inactive roster ignored. No write.

Legacy `GET/POST /centers/<id>/operating-hours/` still exists but is not the canonical write API.

### Center closures (full-day holidays / manual closed days)

**GET/POST** `/centers/<center_id>/availability/closures/`

**PATCH** `/centers/<center_id>/availability/closures/<uuid:pk>/`

```json
{
  "date": "2026-12-25",
  "type": "holiday",
  "reason": "Christmas"
}
```

- `type`: `holiday` | `manual` (required on create)
- `reason`: always required (non-blank) — for holidays, name which holiday
- POST creates a closure; rejects an already-active closure for the same `(center, date)`
- If an inactive row exists for that date, POST reactivates it and updates `type` / `reason`
- PATCH `"is_active": false` reopens the date (soft deactivate); `"is_active": true` closes again; `type` / `reason` also patchable
- Calendar events use `"type": "closure"` plus extras `closure_type` and `reason`
- GET supports `?active=0|1` and optional inclusive `?start=` / `?end=` (`YYYY-MM-DD`)
- GET list order: `date` descending (same-date row order unspecified)
- No DELETE
- Model: `CenterClosure` — **user owns migration** for `type` + `reason` fields

### Associate roster (weekly recurring)

**POST/PATCH** `/centers/<center_id>/availability/associates/<associate_id>/roster/`

Bulk weekly work hours for an associate at this center. Associate comes from the URL (not the body).

After every successful roster write the API **enqueues** an async exception scan (`exception_scan: "queued"` on the response). The job compares busy appointments for that associate against free windows (`center hours ∩ roster − blocks − leaves − closures`) over the next ~90 days. Appointments that no longer fit get an open `AppointmentException` with `source_type=associate_roster` (source id = associate id). Restoring roster clears those open exceptions with `blocker_cleared`.

Run `uv run manage.py process_appointment_exception_scans` on a short cron (about every minute) so queued scans apply. Without that command, jobs stay `pending`.

```json
{
  "entries": [
    {"day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00"},
    {"day_of_week": 1, "start_time": "10:00:00", "end_time": "17:00:00"}
  ]
}
```

- `day_of_week`: int `0`=Monday … `6`=Sunday on the API (stored as `AppointmentDays` char `"0"`…`"6"`)
- `entries` must be non-empty; duplicate days in one request are rejected
- each entry requires `start_time` < `end_time`
- listed days: create, or update times + reactivate if soft-inactive
- **Must fall inside that weekday’s center hours** (inclusive edges). Before open, after close, closed day, or missing hours → 400, nothing saved. All bad days returned together.
- **POST** is additive — omitted days stay as they are
- **PATCH** is a week diff — omitted **active** days are soft-deactivated (`is_active=false`). Empty `entries` rejected (cannot wipe the whole week)
- all entries applied in one atomic transaction
- response: list of the listed (upserted) roster entry representations

Error 400 (global handler puts serializer errors in `detail`; no extra envelope):

```json
{
  "detail": {
    "non_field_errors": ["Roster must fall within center operating hours."],
    "day_errors": [
      {
        "day_of_week": "1",
        "day_of_week_name": "Tuesday",
        "open_time": "09:00:00",
        "close_time": "18:00:00",
        "errors": [
          {
            "code": "before_opening",
            "field": "start_time",
            "message": "Starts before center opening time."
          },
          {
            "code": "after_closing",
            "field": "end_time",
            "message": "Ends after center closing time."
          }
        ]
      },
      {
        "day_of_week": "6",
        "day_of_week_name": "Sunday",
        "errors": [
          {
            "code": "center_closed",
            "field": "day_of_week",
            "message": "Center is closed on this day."
          }
        ]
      }
    ]
  }
}
```

| `code` | When | `field` |
|---|---|---|
| `before_opening` | `start_time` < center `open_time` | `start_time` |
| `after_closing` | `end_time` > center `close_time` | `end_time` |
| `center_closed` | that weekday `is_open=false` | `day_of_week` |
| `center_hours_missing` | no active open hours row | `day_of_week` |

`day_of_week` in `day_errors` is `"0"`…`"6"`. `open_time` / `close_time` omitted when there is no window. Operating-hours PATCH uses the same `day_errors` shape; extra `associate_ids` on each error; codes `before_opening` / `after_closing` / `roster_on_closed_day`; summary `"Operating hours conflict with existing staff roster."`

**GET** `/centers/<center_id>/availability/associate-roster/`

Optional list of roster rows for the center. Supports `?associate=<uuid>` and `?active=0|1` (default active only).
### Associate blocks (one-off or recurring)

**POST/GET** `/centers/<center_id>/availability/associates/<associate_id>/blocks/`

**PATCH** `/centers/<center_id>/availability/associates/<associate_id>/blocks/<block_id>/`

Associate comes from the URL (not the body). POST 201 is `{detail, data}`; `data` is the list of created block rows (never a top-level array).

**One-off:**

```json
{
  "is_recurring": false,
  "start_datetime": "2026-09-01T04:30:00+00:00",
  "end_datetime": "2026-09-01T06:30:00+00:00",
  "reason": "Internal meeting"
}
```

**Recurring (one or more weekdays):**

```json
{
  "is_recurring": true,
  "days_of_week": ["0", "1", "2", "3", "4", "5", "6"],
  "recurring_start_time": "13:00:00",
  "recurring_end_time": "14:00:00",
  "effective_from": "2026-09-01",
  "reason": "Daily admin"
}
```

- `days_of_week`: non-empty array of `"0"`=Monday … `"6"`=Sunday; duplicates rejected
- expands to **one DB row per day** (same times / `effective_from` / reason)
- **No `effective_until`** — recurring blocks stay open-ended; remove with PATCH `is_active=false` (sending `effective_until` is rejected)
- PATCH still edits a single row (`day_of_week` string on that row)
- **Overlap rejection:** active blocks that intersect other active blocks are rejected (`non_field_errors`: "Overlaps an existing unavailability window."). Soft-inactive rows ignored. **Leave always wins:** a leave may overlap an existing associate block; a block may not be created (or reactivated) on top of an existing leave. Leave vs leave still rejects. **Downtime always wins:** room/equipment downtime may overlap an existing block; a block may not be created (or reactivated) on top of an existing downtime. Downtime vs downtime still rejects. Touching endpoints (end == next start) allowed.

### Associate leaves

**POST/GET** `/centers/<center_id>/availability/associates/<associate_id>/leaves/`

**PATCH** `/centers/<center_id>/availability/associates/<associate_id>/leaves/<leave_id>/`

Associate comes from the URL (not the body). `scope=center` uses the URL center; `scope=all_centers` stores `center=null`.

Leaves can be **center-scoped** or **all-centers** (blocks the person everywhere). Leave may overlap an existing associate block; the reverse is rejected.

```json
{
  "scope": "center",
  "start_datetime": "2026-09-05T18:30:00+00:00",
  "end_datetime": "2026-09-06T18:29:59+00:00",
  "reason": "Personal leave"
}
```

Supports full-day, partial-day, and multi-day ranges via `start_datetime` / `end_datetime`.

### Room blocks & downtime

**POST/GET** `/centers/<center_id>/availability/room-blocks/<room_id>/`

**PATCH** `/centers/<center_id>/availability/room-blocks/<room_id>/<block_id>/`

**POST/GET** `/centers/<center_id>/availability/room-downtimes/<room_id>/`

**PATCH** `/centers/<center_id>/availability/room-downtimes/<room_id>/<downtime_id>/`

Room from URL. Block POST 201 `{detail, data}` with `data` = created rows (same create rules as associate blocks: `days_of_week` expand, no `effective_until`). **Downtime = one-off only** (never recurring). Downtime may overlap an existing room block; the reverse is rejected.

**One-off block / downtime** — same calendar day (`settings.TIME_ZONE`): `date` + `start_time` + `end_time`. No multi-day; one POST per day.

```json
{
  "is_recurring": false,
  "date": "2026-09-03",
  "start_time": "08:00:00",
  "end_time": "18:00:00",
  "reason": "Reserved for training"
}
```

Downtime (required `reason`):

```json
{
  "date": "2026-09-03",
  "start_time": "08:00:00",
  "end_time": "18:00:00",
  "reason": "Renovation"
}
```

**Recurring block** — same payload shape as associate recurring (`days_of_week`, `recurring_start_time` / `recurring_end_time`, `effective_from`).

```json
{
  "is_recurring": true,
  "days_of_week": ["0", "2", "4"],
  "recurring_start_time": "11:00:00",
  "recurring_end_time": "13:00:00",
  "effective_from": "2026-09-01",
  "reason": "Weekly hold"
}
```

**Overlap:** downtime always wins vs block on the same room (same rule as leave vs associate block).

### Equipment blocks & downtime

**POST/GET** `/centers/<center_id>/availability/equipment-blocks/<equipment_id>/`

**PATCH** `/centers/<center_id>/availability/equipment-blocks/<equipment_id>/<block_id>/`

**POST/GET** `/centers/<center_id>/availability/equipment-downtimes/<equipment_id>/`

**PATCH** `/centers/<center_id>/availability/equipment-downtimes/<equipment_id>/<downtime_id>/`

Same as rooms. Equip from URL. Blocks: one-off (`date`+times) or recurring (`days_of_week`). Downtime: one-off only. Downtime may overlap an existing equipment block; the reverse is rejected.

---

## Multi-center associates

- **Roster** and **blocks** are always per center
- **Leaves** can be `scope: "center"` (one center only) or `scope: "all_centers"` (every center)
- Associate availability is always queried per center (`/centers/<center_id>/availability/associates/<associate_id>/`)

---

## Bruno collection

Requests live in `bruno/availability/` (center-scoped calendar and write routes).

Subfolders under availability (suggested test order):

1. `operating-hours/` — PATCH then GET
2. `closures/` — POST / GET / PATCH reopen
3. `calendars/` — center / associate / room / equipment GET
4. `associates/` — roster, blocks, leaves
5. `rooms/` — blocks, downtimes
6. `equipment/` — blocks, downtimes

Environment variables: `center_id`, `associate_id`, `room_id`, `equipment_id`, `closure_id`, plus IDs returned from create responses for PATCH examples.

---

## Appointment booking lifecycle

Full design: `docs/superpowers/specs/2026-08-28-appointments-design.md` §6.

Staff book creates `confirmed` immediately (no `pending` / `confirmation_pending`).

| # | Flow |
|---|---|
| 1 | `confirmed` → `checked_in` → `in_progress` → `completed` |
| 2 | same as 1 + `mark_late` while `in_progress` |
| 3 | `confirmed` → `cancelled` |
| 4 | `confirmed` → `no_show` |
| 5 | `confirmed` → `checked_in` → `cancelled` |
| 6 | `confirmed` → `checked_in` → reschedule → `confirmed` |

Waiting-room (`checked_in`) is still reversible (cancel or reschedule). Session started (`in_progress`) is not. Reschedule always lands `confirmed`.

Busy (exclusive reservation): `confirmed`, `checked_in`, `in_progress`. Not busy: `cancelled`, `no_show`, `completed`.

---

## Implementation notes (for engineers)

| Topic | Location |
|---|---|
| Models | `appointments/models.py` |
| Interval math | `appointments/utils/intervals.py` |
| Calendar computation | `appointments/utils/calendar.py` |
| Views / serializers | `appointments/views.py`, `appointments/serializers.py` |
| URL wiring | `accounts/centers/urls.py`, `accounts/associates/urls.py` |

**ponytail shortcuts:**

- Center timezone defaults to `settings.TIME_ZONE` — no per-center timezone field yet
- Rooms/equipment base availability = center operating hours (legacy `RoomSchedule` / `EquipmentSchedule` not used)
- User generates migrations (`makemigrations` not run by agents)
- Availability write responses may include top-level `exception_scan`: `queued` \| `completed` \| `resolved` \| `skipped` (sibling of `detail` / `data`; `data` shape unchanged)
- Ops: cron `process_appointment_exception_scans` (~1 min) + optional nightly `reconcile_appointment_exception_flags` + `cleanup_appointment_idempotency_keys`

---

*Last updated: 2026-09-03*
