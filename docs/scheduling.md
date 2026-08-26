# Scheduling Module

## Overview

The scheduling module computes appointment availability by intersecting multiple resource calendars and subtracting busy intervals — entirely in-memory using interval arithmetic. No external calendar service is required.

```
Available = Center ∩ Associate [∩ Room] [∩ Equipment]
            − Holidays − Blocks − Appointments − Maintenance
```

Nothing is pre-generated or stored. Schedules are stored as recurring rules (day-of-week + time range), and concrete intervals are computed on-the-fly for any queried date range.

## Architecture

```
appointments/utils/
├── intervals.py    # Pure interval arithmetic (no Django dependency)
├── scheduling.py   # DB-aware functions that compose intervals
├── db.py           # Appointment CRUD helpers
└── constants.py    # Enums (AppointmentDays, AppointmentModes, etc.)
```

### intervals.py — Pure Functions

All functions operate on sorted lists of `(datetime, datetime)` tuples. No Django imports, no database access. Fully unit-testable in isolation.

| Function | Purpose |
|---|---|
| `expand_weekly_schedule` | Rule → concrete intervals for a date range |
| `merge_intervals` | Combine overlapping/adjacent intervals |
| `intersect_intervals` | Overlap of two interval lists |
| `intersect_many` | Chain intersection across N lists |
| `subtract_intervals` | Remove busy intervals from available |
| `split_into_slots` | Break free windows into fixed-duration slots |

### scheduling.py — DB-Aware Functions

Queries Django models, expands them into intervals using `intervals.py`, and composes the result.

| Function | Purpose |
|---|---|
| `find_available_slots` | Main entry point — returns bookable `(start, end)` slots |
| `get_available_periods` | Free windows without slot splitting (for calendar views) |
| `get_blocked_periods` | Union of holidays, leave, maintenance |
| `get_scheduled_periods` | Existing appointments and equipment bookings |
| `get_schedule_intervals` | Raw recurring schedule for a single resource |
| `get_day_summary` | Single-day breakdown: scheduled / available / blocked |

## Data Flow

### What is stored in the database

| Model | What it represents | Pattern |
|---|---|---|
| `CenterOperatingHour` | Center open/close times | Recurring (day-of-week) |
| `Schedule` | Associate working hours at a center | Recurring (day-of-week) |
| `RoomSchedule` | Room operational/maintenance windows | Recurring (day-of-week) |
| `EquipmentSchedule` | Equipment operational/maintenance windows | Recurring (day-of-week) |
| `CenterClosure` | Center closed on a specific date | One-off (date) |
| `BlockedPeriod` | Associate unavailable (leave, etc.) | One-off (datetime range) |
| `Appointment` | Booked appointment | One-off (datetime range) |
| `EquipmentBooking` | Equipment reserved for an appointment | One-off (datetime range) |
| `EquipmentMaintenance` | Equipment under maintenance | One-off (datetime range) |

### What is computed at query time

```
Query: "Find 30-min slots for Dr. Smith in Room 1 with DEXA scanner, Feb 1-7"

1. EXPAND recurring rules into concrete intervals for Feb 1-7:
   Center hours:     [(Mon 9-18), (Tue 9-18), (Wed 9-18), ...]
   Dr. Smith:        [(Mon 9-13), (Mon 14-17), (Tue 10-16), ...]
   Room 1:           [(Mon 8-20), (Tue 8-20), ...]
   DEXA scanner:     [(Mon 9-17), (Wed 9-17), ...]

2. INTERSECT all layers (two-pointer merge):
   Common windows:   [(Mon 9-13), (Mon 14-17), (Wed 9-17), ...]

3. COLLECT busy intervals:
   Holiday Feb 3:    [(Tue 00:00 - 23:59)]
   Dr. Smith leave:  []
   Existing appts:   [(Mon 10:00-10:30), (Wed 11:00-12:00)]
   Room maintenance: [(Wed 13:00-14:00)]
   DEXA bookings:    [(Mon 15:00-15:45)]  ← includes setup/cooldown
   DEXA maintenance: []

4. MERGE busy intervals:
   Busy (sorted):    [(Mon 10:00-10:30), (Mon 15:00-15:45), (Tue 00:00-23:59),
                       (Wed 11:00-12:00), (Wed 13:00-14:00)]

5. SUBTRACT busy from available:
   Free windows:     [(Mon 9:00-10:00), (Mon 10:30-13:00), (Mon 14:00-15:00),
                       (Wed 9:00-11:00), (Wed 12:00-13:00), (Wed 14:00-17:00)]

6. SPLIT into 30-min slots (with buffer):
   Bookable slots:   [(Mon 9:00-9:30), (Mon 9:40-10:00 ✗ too short), ...]
```

## Usage Examples

### Find bookable appointment slots

```python
from datetime import date
from appointments.utils.scheduling import find_available_slots

slots = find_available_slots(
    associate=dr_smith,
    center=bangalore_center,
    query_start=date(2026, 2, 1),
    query_end=date(2026, 2, 7),
    duration_minutes=30,
    buffer_minutes=10,
    room=consultation_room_1,
    equipment=dexa_scanner,
)
# [(datetime, datetime), ...]
```

### Get free windows for a calendar view

```python
from appointments.utils.scheduling import get_available_periods

free_windows = get_available_periods(
    associate=dr_smith,
    center=bangalore_center,
    query_start=date(2026, 2, 1),
    query_end=date(2026, 2, 7),
    room=consultation_room_1,
)
# [(Mon 9:00-10:00, Mon 10:30-13:00, ...), ...]
```

### Get all blocked periods

```python
from appointments.utils.scheduling import get_blocked_periods

blocks = get_blocked_periods(
    associate=dr_smith,
    center=bangalore_center,
    query_start=date(2026, 2, 1),
    query_end=date(2026, 2, 7),
    room=consultation_room_1,
    equipment=dexa_scanner,
)
# Holidays + leave + maintenance windows
```

### Get existing bookings

```python
from appointments.utils.scheduling import get_scheduled_periods

booked = get_scheduled_periods(
    query_start=date(2026, 2, 1),
    query_end=date(2026, 2, 7),
    associate=dr_smith,
    equipment=dexa_scanner,
)
# Existing appointment intervals + equipment booking intervals
```

### Single-day breakdown

```python
from appointments.utils.scheduling import get_day_summary

summary = get_day_summary(
    associate=dr_smith,
    center=bangalore_center,
    target_date=date(2026, 2, 3),
    room=consultation_room_1,
)
# {
#     'scheduled': [(10:00, 10:30), (14:00, 15:00)],
#     'available': [(9:00, 10:00), (10:30, 13:00), (15:00, 17:00)],
#     'blocked':   [],
# }
```

### Raw schedule for a single resource

```python
from appointments.utils.scheduling import get_schedule_intervals

room_hours = get_schedule_intervals(
    resource=consultation_room_1,
    resource_type='room',
    query_start=date(2026, 2, 1),
    query_end=date(2026, 2, 7),
)
# Operational windows for the room, expanded from recurring rules
```

## Complexity Analysis

### Time Complexity

Let the following variables represent input sizes for a query over `D` days:

| Variable | Meaning | Typical value |
|---|---|---|
| `S` | Schedule rules per resource | 1-7 (one per weekday) |
| `R` | Number of resources to intersect | 2-4 |
| `D` | Days in query range | 1-30 |
| `B` | Total busy intervals (appointments + blocks + holidays + maintenance) | 0-100 |
| `K` | Output slots | 0-500 |

**Step-by-step:**

| Step | Operation | Complexity |
|---|---|---|
| Expand schedules | Iterate weekdays in range per rule | `O(S × D)` per resource |
| Merge intervals | Sort + linear scan | `O(N log N)` where `N = S × D` |
| Intersect (pair) | Two-pointer sweep | `O(N + M)` for lists of size N, M |
| Intersect (all) | Chain R-1 pairwise intersections | `O(R × S × D)` |
| Collect busy | DB queries + sort + merge | `O(B log B)` |
| Subtract | Linear sweep | `O(S × D + B)` |
| Split into slots | Linear over free windows | `O(K)` |

**Overall: `O(R × S × D + B log B + K)`**

For a typical query (7-day range, 4 resources, 50 existing bookings):

```
R=4, S=7, D=7, B=50, K≈100
→ 4 × 7 × 7 + 50 × log(50) + 100
→ 196 + 282 + 100
→ ~578 operations
```

This is negligible. The database queries dominate runtime, not the computation.

### Space Complexity

`O(S × D + B + K)` — proportional to the expanded intervals, busy intervals, and output slots. For a 30-day query this is at most a few thousand tuples in memory.

### Database Queries

For a single `find_available_slots` call with all optional resources:

| Query | Count |
|---|---|
| Center operating hours | 1 |
| Associate schedules | 1 |
| Room schedules (operational) | 1 |
| Equipment schedules (operational) | 1 |
| Center holidays | 1 |
| Associate blocked periods | 1 |
| Appointments | 1 |
| Room schedules (maintenance) | 1 |
| Equipment bookings | 1 |
| Equipment maintenance | 1 |
| **Total** | **10** |

All queries are filtered by date range and hit indexed fields. Each returns a small result set. Total DB time is typically under 10ms.

### Comparison with External Calendar API

| Metric | Local interval math | Google Calendar API |
|---|---|---|
| Latency per query | <10ms (in-memory) | 200-500ms (network) |
| DB queries | 10 simple indexed queries | 0 (but 1+ API calls) |
| Failure mode | Only fails if DB is down | Fails on API outage, rate limit, auth expiry |
| Concurrency | Unlimited (stateless computation) | 500 req/100s per service account |
| Atomicity | Can wrap in DB transaction | No transactional guarantee |
| Recurrence support | Weekly patterns (sufficient for this domain) | Full RFC 5545 RRULE |
| Testability | Pure functions, no mocking needed | Requires API mocking |

### Scaling Considerations

The module handles scheduling at the **individual resource** level. Queries are always scoped to a specific (associate, center, room?, equipment?) combination. This means:

- Adding more centers, rooms, or associates does not increase per-query cost.
- Query cost grows linearly with the date range (`D`) and the number of existing bookings (`B`) in that range.
- For a 30-day range with 200 bookings per associate, the computation is still under 1ms.

The only scenario requiring optimization would be a batch operation like "find all available rooms across all centers for the next 30 days" — which would require one query per room. This can be parallelized or cached at the API layer if needed.
