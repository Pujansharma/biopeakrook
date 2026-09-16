# Appointments — Frontend API

Staff-only (admin or associate JWT). Center is always in the URL path.

| Area | Base path |
|---|---|
| Booking + lifecycle + exceptions + ops | `/centers/<center_id>/appointments/` |
| Care teams | `/centers/<center_id>/care-teams/` |
| Availability (hours, calendar, roster, blocks…) | `/centers/<center_id>/availability/` |

**Auth:** `Authorization: Bearer <access_token>`

**Headers**

| Header | Booking / care-teams / ops | Availability |
|---|---|---|
| `X-Center-ID` | Not required | Associates: must match URL `center_id` |
| `Idempotency-Key` | Optional on book only | — |

**Envelope (always)**

```json
{ "detail": "…", "data": { } }
```

`data` is an object, list, or omitted. Never a bare top-level array. No `success` key.

Bruno: `bruno/appointments/`, `bruno/availability/`.

---

## 1. Concepts FE must know

### Status machine

Book lands **`confirmed`** (no pending).

| Action | From | To |
|---|---|---|
| check-in | `confirmed` | `checked_in` |
| start | `checked_in` | `in_progress` |
| mark-late | `in_progress` | `in_progress` (flags late) |
| complete | `in_progress` | `completed` |
| cancel | `confirmed` \| `checked_in` | `cancelled` |
| no-show | `confirmed` | `no_show` |
| reschedule | `confirmed` \| `checked_in` | `confirmed` |

`in_progress` → cancel/reschedule **blocked**. Exception ack only.

**Busy** (blocks slots): `confirmed`, `checked_in`, `in_progress`.  
Not busy: `completed`, `cancelled`, `no_show`.

### Time / buffers

- Wall time: `start` / `end` (session).
- Exclusive reservation: `exclusive_start` / `exclusive_end` = start−buffer_before … end+buffer_after (from center service assignment). Overlap checks use exclusive range.
- Customer busy is **global** (any center).
- Day boundaries use center timezone (today: `Asia/Kolkata` / `settings.TIME_ZONE`). Stored datetimes are UTC.

### How free time is computed

```
available = base − blocks − leaves/downtimes − closures − busy appointments
```

| Resource | Base | Subtract |
|---|---|---|
| Center | Weekly operating hours | Closures |
| Associate | Center hours ∩ roster | Blocks, leaves, closures |
| Room / equipment | Center hours | Blocks, downtimes, closures |

Slots are computed on demand (not pre-stored). Cap **200 slots/day** (`truncated: true` if more). Slots with `start` before request time are omitted (today’s past windows). Past calendar dates → 400 `"Date cannot be in the past."`

### Preferred (slots) vs flattened book

Find Slots still nests resources under `preferred`. Book/reschedule send the same IDs at the **top level**. No `associates[]` pin. Server stamps hats from `doctor_id` / `specialty_id` / `care_team_id`.

- `care_team_id` **XOR** `doctor_id` / `specialty_id` (doctor + specialty OK together).
- Allowed staff combos: care_team · doctor · specialty · doctor+specialty. Plus `room_id` (required in_person; forbidden virtual).
- `specialty_id` = service-mapped person; `doctor_id` may be extra (not on the service). `doctor_id` must hold **exactly one** live role with `"doctor"` in the name. `specialty_id` stamps a live **non-doctor** hat that is an **active role requirement on this service** (associate may hold many specialty hats). Zero overlap, or service has no role requirements → 400 `"specialty_id must hold a live non-doctor role mapped to this service."` Two+ mapped hats → stamp one (stable role `pk`). Same person both IDs → 400. Same associate cannot appear twice on an appointment.
- Old `health_coach_id` → 400 `"Use specialty_id instead of health_coach_id."`
- Room: active at this center, `room_type_ref` set and active. If assignment has room-type requirements, type must be in that set (OR).
- Equipment: FE picks. Room with ≥1 bookable unit (`is_active` + type set + type `is_active` + allotted to that room) → `equipment_id` **required**. Room with 0 bookable → omit/`null`; sending an id → 400. Virtual → no `equipment_id`. Chosen unit must belong to the room. No auto-pick of “first” equipment.
- Find Slots: `preferred` required. Book/reschedule: same staff XOR + room/equipment rules at top level.
- `care_team_id` with **zero live members** → 400 `"Care team has no live members at this center."`

### Weekday codes

`"0"`=Mon … `"6"`=Sun (strings on most APIs). Roster `day_of_week` is **int** 0–6.

### Soft delete

No DELETE on availability / care teams. `PATCH { "is_active": false }`.

### Availability write side effect

Many availability writes may return sibling field:

```json
{ "detail": "…", "data": { }, "exception_scan": "queued" }
```

Values: `queued` | `completed` | `resolved` | `skipped`. FE can ignore or show “scan queued”.

---

## 2. Appointment shapes

### List item / nested appointment

```json
{
  "id": "uuid",
  "code": "string",
  "start": "ISO-8601",
  "end": "ISO-8601",
  "status": "confirmed",
  "modality": "in_person",
  "is_late": false,
  "late_by": null,
  "has_open_exception": false,
  "customer": { "id": "uuid", "name": "…" },
  "service": { "id": "uuid", "name": "…" },
  "care_team": { "id": "uuid", "name": "…" },
  "associates": [
    { "id": "uuid", "name": "…", "role": { "id": "uuid", "name": "…" } }
  ],
  "room": { "id": "uuid", "name": "…" },
  "equipment": { "id": "uuid", "name": "…" }
}
```

`care_team` / `room` / `equipment` may be `null`.

### Detail (list fields +)

```json
{
  "duration_minutes": 40,
  "buffer_before_minutes": 0,
  "buffer_after_minutes": 0,
  "exclusive_start": "ISO-8601",
  "exclusive_end": "ISO-8601",
  "cancel_reason": "",
  "exception_resolution_hint": null,
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

`exception_resolution_hint`: string when `has_open_exception`; null otherwise.

---

## 3. Booking APIs

Base: `/centers/<center_id>/appointments/`

### POST `…/slots/` — Find slots

**Purpose:** One calendar day of bookable pinned combos for a customer + service. Past calendar dates → 400. Past starts today (`start` < now) are omitted.

**Body (required)**

| Field | Type | Notes |
|---|---|---|
| `customer_profile_id` | UUID | Active profile assigned to this center |
| `service_id` | UUID | Active service assigned to this center |
| `modality` | `"virtual"` \| `"in_person"` | Not `"both"` |
| `date` | `YYYY-MM-DD` | Today or future in `settings.TIME_ZONE` (`Asia/Kolkata`). Past → 400 `"Date cannot be in the past."` |

**Body (`preferred` required)**

```json
"preferred": {
  "room_id": "uuid",
  "equipment_id": "uuid",
  "care_team_id": "uuid",
  "doctor_id": "uuid",
  "specialty_id": "uuid"
}
```

Omit empty preferred keys (blank UUID → 400). Never send `care_team_id` with doctor/specialty.

**Staff on each slot** comes from preferred `care_team_id` / `doctor_id` / `specialty_id` only (no leftover auto-fill from service role pools). Omitting staff → 400. Slot **echoes nested resources** (omit key if not in preferred). No `associates[]`. No bare `*_id`. Book still flattened IDs (`slot.doctor.id` → `doctor_id`, etc).

`preferred.room_id` required for `in_person`. `preferred.equipment_id` required when that room has ≥1 bookable equipment; omit when the room has none.

**Example payloads**

```json
{
  "customer_profile_id": "…",
  "service_id": "…",
  "modality": "in_person",
  "date": "2026-09-05",
  "preferred": { "specialty_id": "…", "room_id": "…", "equipment_id": "…" }
}
```

```json
{
  "customer_profile_id": "…",
  "service_id": "…",
  "modality": "in_person",
  "date": "2026-09-05",
  "preferred": { "care_team_id": "…", "room_id": "…" }
}
```

```json
{
  "customer_profile_id": "…",
  "service_id": "…",
  "modality": "virtual",
  "date": "2026-09-05",
  "preferred": { "doctor_id": "…", "specialty_id": "…" }
}
```

**Response `data`**

```json
{
  "date": "2026-09-05",
  "timezone": "Asia/Kolkata",
  "duration_minutes": 40,
  "buffer_before_minutes": 0,
  "buffer_after_minutes": 0,
  "truncated": false,
  "slots": [
    {
      "start": "ISO-8601",
      "end": "ISO-8601",
      "care_team": { "id": "uuid", "name": "…" },
      "doctor": { "id": "uuid", "name": "…" },
      "specialty": {
        "id": "uuid",
        "name": "…",
        "role": { "id": "uuid", "name": "…" }
      },
      "room": { "id": "uuid", "name": "…" },
      "equipment": { "id": "uuid", "name": "…" }
    }
  ]
}
```

Each slot = one combo. Nested keys only when present (virtual: no room/equipment; care-team XOR people; no equipment when room has none). FE book: extract `id` from nested objects into flattened `doctor_id` / `specialty_id` / `care_team_id` / `room_id` / `equipment_id`.

**Common 400:** invalid customer/service for center · modality not supported · room required for in_person · equipment_id required when room has bookable units · care_team XOR people · service duration missing · no staff (`care_team_id` / `doctor_id` / `specialty_id`) · start in the past.

---

### POST `…/` — Book

**Purpose:** Create confirmed appointment.

**Headers:** optional `Idempotency-Key` (UUID). Same key + same payload → 200 existing detail (availability is **not** re-checked). Same key + different payload → **409**.

**Body**

| Field | Required | Notes |
|---|---|---|
| `customer_profile_id` | yes | |
| `service_id` | yes | |
| `modality` | yes | `virtual` \| `in_person` |
| `start` | yes | ISO datetime (from slot). Must be in the future. `end` must equal `start` + assignment duration. Past → 400 `"Date cannot be in the past."` |
| `end` | yes | |
| `room_id` | in_person | Forbidden for virtual |
| `equipment_id` | if room has bookable equipment | null when room has none; forbidden for virtual |
| `doctor_id` / `specialty_id` | XOR care_team | Doctor + specialty OK together |
| `care_team_id` | XOR people | |
| `notes` | no | omit/`null` on reschedule keeps existing; `""` clears |

**Book example**

```json
{
  "customer_profile_id": "…",
  "service_id": "…",
  "modality": "in_person",
  "start": "2026-09-05T04:00:00Z",
  "end": "2026-09-05T04:40:00Z",
  "specialty_id": "…",
  "room_id": "…",
  "equipment_id": "…"
}
```

**Response:** 201 `data` = appointment detail. Idempotent replay: 200 same shape.

**Common 400:** staff XOR · room/equipment rules · slot no longer available · invalid IDs for center · duration mismatch.

---

### GET `…/` — List (calendar)

**Purpose:** Appointments overlapping a day/week/month window. With `search` and no `start`, matching appointments for this center across all dates.

**Query**

| Param | Default | Values |
|---|---|---|
| `start` | today (no `search`); omit with `search` = all history | `YYYY-MM-DD` |
| `granularity` | `week` | `day` \| `week` \| `month` — used only when a date window applies |
| `search` | omit | string — customer name / email / phone, appointment `code`, service name |
| `associate_id` | omit | UUID — appointment has this associate on `associates[]` |
| `role_id` | omit | UUID — appointment has this role on `associates[]` |
| `service_id` | omit | UUID |
| `room_id` | omit | UUID |
| `equipment_id` | omit | UUID |
| `equipment_type_id` | omit | UUID — via booked equipment |
| `status` | omit | single: `confirmed` \| `checked_in` \| `in_progress` \| `completed` \| `cancelled` \| `no_show` |
| `care_team_id` | omit | UUID |

All optional filters AND with the date window when a window applies. `search` is OR across fields, then AND with UUID/`status` filters. `associate_id` and `role_id` together = **OR** (appointment has this associate **or** this role on any link). Blank/omit = no filter. `associate_id` / `role_id` match `associates[]` on the appointment (always present on booked rows).

**Date window**

| `search` | `start` | Date filter |
|---|---|---|
| omit | omit | today + default `granularity` (`week`) |
| omit | sent | window for that `start` + `granularity` |
| set | omit | **none** — all matching appointments at this center |
| set | sent | window for that `start` + `granularity` (narrows search) |

Omit `start` to search history. Do not send empty `start=`. Junk UUID → 400 `Invalid <param>.`. Junk `status` → 400.

Week = Mon–Sun containing `start`. Month = calendar month.

**Response `data`**

```json
{
  "appointments": [ /* list items */ ],
  "truncated": false,
  "total_count": 12
}
```

Week/month and unscoped `search` (no `start`) hard-cap **500** via `LIMIT 501` (no full-table `COUNT(*)`). `truncated: true` if more than 500; `total_count` = returned row count (≤500). Day window is uncapped and still uses exact `count()`. Windowed lists stay chronological (`start` ascending); unscoped search is newest first.

---

### GET `…/<appointment_id>/` — Detail

**Purpose:** Full appointment.  
**Response `data`:** detail shape.

---

### Lifecycle POSTs

All return appointment **detail** in `data`. Empty body unless noted.

| Method | Path | Body | Allowed from |
|---|---|---|---|
| POST | `…/<id>/check-in/` | — | `confirmed` |
| POST | `…/<id>/start/` | — | `checked_in` |
| POST | `…/<id>/complete/` | — | `in_progress` |
| POST | `…/<id>/no-show/` | — | `confirmed` |
| POST | `…/<id>/mark-late/` | `{ "late_by": <int ≥1> }` | `in_progress` |
| POST | `…/<id>/cancel/` | `{ "reason": "<string max 500>" }` | `confirmed` \| `checked_in` |
| POST | `…/<id>/reschedule/` | same as **Book** body | `confirmed` \| `checked_in` |

Reschedule lands `confirmed`. Same flattened body as book. Cannot change `customer_profile_id` or `service_id`. Overlap → `"Slot no longer available."`

Illegal transition → validation error (`Cannot perform '…' from status '…'`).

---

## 4. Exceptions

Base: `/centers/<center_id>/appointments/exceptions/`

Open exceptions = appointment conflicts with leave/block/roster/downtime/closure after the fact.

### GET `…/exceptions/`

**Query:** `status` = `open` (default) \| `resolved`. Junk → 400.  
Paginated (`page`, `limit`).

**Response `data`:** page of:

```json
{
  "id": "uuid",
  "status": "open",
  "resolution": null,
  "detected_at": "ISO-8601",
  "resolved_at": null,
  "appointment": { /* list item */ },
  "source": {
    "source_type": "associate_leave",
    "source_id": "uuid",
    "source_label": "…",
    "source_start": "ISO-8601",
    "source_end": "ISO-8601"
  }
}
```

`source_type`: `associate_leave` \| `associate_block` \| `associate_roster` \| `room_block` \| `equipment_block` \| `room_downtime` \| `equipment_downtime` \| `closure`.

### GET `…/exceptions/count/`

**Response `data`:** `{ "open_count": 3 }`

### POST `…/exceptions/<exception_id>/acknowledge/`

**Purpose:** Resolve without changing appointment status. Only path for open exceptions while `in_progress`.  
**Body:** none.  
**Response `data`:** exception list item (resolved).

Also auto-resolved by cancel (`cancelled`) or reschedule (`rescheduled`).

---

## 5. Operations dashboards

Base: `/centers/<center_id>/appointments/operations/`  
Cached ~10 min; invalidated on book/lifecycle.

**Shared query**

| Param | Notes |
|---|---|
| `start` | `YYYY-MM-DD` (default today UTC date). Junk / impossible date → 400 `"Invalid start date. Use YYYY-MM-DD."` |
| `end` | optional end date; if omitted use `granularity`. Junk → 400 `"Invalid end date. Use YYYY-MM-DD."` End before start → 400 `"End date cannot be before start date."` |
| `granularity` | default `week` — used when `end` omitted. Junk → 400 `"Invalid granularity. Use day, week, or month."` |

Booked minutes / hours / appointment counts / utilization / bottleneck dependents count only **busy** statuses (`confirmed`, `checked_in`, `in_progress`). Cancelled, completed, and no-show are excluded.

### GET `…/operations/overview/`

```json
{
  "center_id": "uuid",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "appointment_count": 0,
  "booked_minutes": 0,
  "booked_hours": 0,
  "status_breakdown": { "confirmed": 2 },
  "service_breakdown": [
    {
      "service_id": "uuid",
      "service_name": "…",
      "booked_minutes": 0,
      "appointment_count": 0
    }
  ],
  "peak_hours": [{ "hour": 10, "appointment_count": 3 }]
}
```

### GET `…/operations/staff/` | `…/rooms/` | `…/equipment/`

`data` = **array** of capacity rows:

```json
{
  "associate_id": "uuid",
  "name": "…",
  "available_minutes": 0,
  "available_hours": 0,
  "booked_minutes": 0,
  "booked_hours": 0,
  "utilization": 0.0
}
```

Rooms use `room_id` + `name`. Equipment use `equipment_id` + `name`.

### GET `…/operations/capacity/`

```json
{
  "center_id": "uuid",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "staff": {
    "resource_type": "staff",
    "resource_count": 0,
    "available_minutes": 0,
    "available_hours": 0,
    "booked_minutes": 0,
    "booked_hours": 0,
    "utilization": 0.0
  },
  "rooms": { /* same shape, resource_type rooms */ },
  "equipment": { /* same shape, resource_type equipment */ }
}
```

### GET `…/operations/bottlenecks/`

`data` = array. Item types:

- `room_downtime` / `equipment_downtime`: `resource_id`, `resource_name`, `start`, `end`, `dependent_appointment_count`, `reason`
- `staff_underutilized`: `resource_id`, `resource_name`, `utilization`, `available_hours`, `booked_hours` (util &lt; 0.2)

---

## 6. Care teams

Base: `/centers/<center_id>/care-teams/`

### Care team shape

```json
{
  "id": "uuid",
  "name": "Alpha",
  "is_active": true,
  "members_count": 2,
  "members": [
    {
      "associate": { "id": "uuid", "name": "…", "is_active": true },
      "role": { "id": "uuid", "name": "…", "is_active": true }
    }
  ],
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

### GET `…/care-teams/`

**Query:** `search` (name), `active=0|1` (omit = both), `members_live=0|1` (omit/junk = no filter; `1` = every member live at center with mapped role active; `0` = any member inactive or mapped role inactive/unmapped; not the bookable-team picker — booking still expands leftover live members), `page`, `limit`. Independent of `active`. Team always has ≥2 members.

### POST `…/care-teams/`

```json
{
  "name": "Alpha",
  "members": [
    { "associate_id": "…", "role_id": "…" },
    { "associate_id": "…", "role_id": "…" }
  ]
}
```

Min 2 members. Unique associate + unique role per team. Name unique per center (case-insensitive). Associates must be live-assigned with that active role.

### GET / PATCH `…/care-teams/<id>/`

PATCH partial. `members` present = full replace (still min 2). Deactivate: `{ "is_active": false }` — also soft-deactivates that team's active availability blocks (slots reopen). Reactivating the team does **not** revive those blocks.

---

## 7. Availability — calendars (read)

Base: `/centers/<center_id>/availability/`  
Associates: send matching `X-Center-ID`.

### Query (all calendars)

| Param | Default | Values |
|---|---|---|
| `start` | today | `YYYY-MM-DD` |
| `granularity` | center: **`week`**; others: **`day`** | `day` \| `week` \| `month` |

### Endpoints

| GET | Purpose |
|---|---|
| `…/availability/` | Center hours − closures |
| `…/availability/associates/<associate_id>/` | Associate at this center |
| `…/availability/care-teams/<care_team_id>/` | Care team at this center |
| `…/availability/rooms/<room_id>/` | Room |
| `…/availability/equipment/<equipment_id>/` | Equipment |

### Response `data`

```json
{
  "resource_type": "center",
  "center_id": "uuid",
  "timezone": "Asia/Kolkata",
  "start": "YYYY-MM-DD",
  "end": "YYYY-MM-DD",
  "granularity": "week",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_of_week": "2",
      "day_of_week_name": "Wednesday",
      "base_windows": [{ "start": "ISO", "end": "ISO" }],
      "available_windows": [{ "start": "ISO", "end": "ISO" }],
      "events": [
        {
          "type": "closure",
          "id": "uuid",
          "start": "ISO",
          "end": "ISO",
          "closure_type": "holiday",
          "reason": "…"
        }
      ]
    }
  ]
}
```

- Associate calendar adds `associate_id`. Base = center ∩ roster. Also subtracts blocks from care teams this associate is a live member of (`care_team_block` / `care_team_block_recurring`).
- Care team calendar adds `care_team_id`. Base = **intersect** of live members' (center ∩ roster). `events` includes team blocks **and** member associate events (blocks/leaves with `associate_id`, plus those members' appointments) and closures.
- Event `type` examples: `closure`, `associate_block`, `associate_block_recurring`, `associate_leave` (+ `scope`), `care_team_block`, `care_team_block_recurring`, room/equipment block/downtime variants.
- `base_windows` = before subtractors; `available_windows` = after.

---

## 8. Availability — write APIs

All under `/centers/<center_id>/availability/`. List GETs support `?active=0|1` (omit → active only unless noted). No DELETE.

### Operating hours

**GET / PATCH** `…/operating-hours/`

PATCH body:

```json
{
  "open_time": "09:00:00",
  "close_time": "18:00:00",
  "days": ["0", "1", "2", "3", "4", "5"],
  "closed_days": ["6"]
}
```

- Open days share times; `closed_days` → closed. Days omitted from both lists unchanged.
- Rejects if active roster would fall outside new window (`detail.day_errors`).

### Closures

**GET / POST** `…/closures/`  
**PATCH** `…/closures/<id>/`

POST:

```json
{
  "date": "2026-12-25",
  "type": "holiday",
  "reason": "Christmas"
}
```

`type`: `holiday` \| `manual`. `reason` required. GET: `active`, optional `start`/`end` dates. Order: `date` desc. PATCH `is_active: false` reopens day.

### Associate roster

**POST / PATCH** `…/associates/<associate_id>/roster/`

```json
{
  "entries": [
    { "day_of_week": 0, "start_time": "09:00:00", "end_time": "17:00:00" }
  ]
}
```

- `day_of_week` int 0–6. Non-empty. Duplicate days rejected. Must sit inside center hours.
- **POST** additive (omit day = leave alone).
- **PATCH** week-diff (omit active day = soft-deactivate). Empty `entries` rejected.
- Response may include `exception_scan`.

**GET** `…/associate-roster/?associate=<uuid>&active=0|1` — center roster list.

### Associate blocks

**GET / POST** `…/associates/<associate_id>/blocks/`  
**PATCH** `…/associates/<associate_id>/blocks/<id>/`

One-off:

```json
{
  "is_recurring": false,
  "start_datetime": "2026-09-01T04:30:00+00:00",
  "end_datetime": "2026-09-01T06:30:00+00:00",
  "reason": "Internal meeting"
}
```

Recurring (one row per weekday; no `effective_until`):

```json
{
  "is_recurring": true,
  "days_of_week": ["0", "1", "2"],
  "recurring_start_time": "13:00:00",
  "recurring_end_time": "14:00:00",
  "effective_from": "2026-09-01",
  "reason": "Daily admin"
}
```

POST 201: `data` = **array of created rows**. Cannot overlap another active block or an active leave.

### Associate leaves

**GET / POST** `…/associates/<associate_id>/leaves/`  
**PATCH** `…/associates/<associate_id>/leaves/<id>/`

```json
{
  "scope": "center",
  "start_datetime": "2026-09-05T18:30:00+00:00",
  "end_datetime": "2026-09-06T18:29:59+00:00",
  "reason": "Personal leave"
}
```

`scope`: `center` (URL center) \| `all_centers`. Leave may overlap blocks; block cannot land on leave.

### Care team blocks

**GET / POST** `…/care-teams/<care_team_id>/blocks/`  
**PATCH** `…/care-teams/<care_team_id>/blocks/<id>/`

Same body as associate blocks (one-off datetimes or recurring `days_of_week`). No team roster or leave — those stay on associates.

- POST 201: `data` = **array of created rows**.
- Cannot overlap another active block on the **same team**. May overlap a member's personal block/leave.
- Applies to **current** live members (not snapshotted). Shows on the team calendar and on each member's associate calendar + slots.
- Recurring POST → `exception_scan: queued`. Scan hits appointments with `Appointment.care_team` = this team (not every solo member apt).

### Room blocks & downtimes

**Blocks:** `…/room-blocks/<room_id>/` (+ `/<id>/` PATCH)  
**Downtimes:** `…/room-downtimes/<room_id>/` (+ `/<id>/` PATCH)

One-off block / downtime (same local day only):

```json
{
  "is_recurring": false,
  "date": "2026-09-03",
  "start_time": "08:00:00",
  "end_time": "18:00:00",
  "reason": "…"
}
```

Downtime body omits `is_recurring` (always one-off); `reason` required.

Recurring block: same shape as associate recurring (`days_of_week`, times, `effective_from`).

Downtime may overlap block; block cannot land on downtime.

### Equipment blocks & downtimes

Same contracts as rooms:

- `…/equipment-blocks/<equipment_id>/`
- `…/equipment-downtimes/<equipment_id>/`

### Multi-center associates

- Roster + blocks = per center.
- Leaves: `center` or `all_centers`.
- Always query associate calendar per center URL.

---

## 9. FE flows (short)

1. **Book:** Find Slots → pick slot → Book with `id`s from nested `doctor` / `specialty` / `care_team` / `room` / `equipment` flattened (+ optional Idempotency-Key).
2. **Day-of:** check-in → start → (optional mark-late) → complete. Or no-show from confirmed. Cancel/reschedule only before start.
3. **Exception badge:** `GET exceptions/count/` → list open → cancel / reschedule / acknowledge.
4. **Setup schedule:** PATCH operating-hours → roster → calendars to verify → blocks/leaves/downtimes as needed.
5. **Ops board:** overview + capacity + bottlenecks for selected range.

---

## 10. Common errors (FE copy)

| Message / situation | When |
|---|---|
| `Invalid customer profile for this center.` | Profile missing / inactive / other center |
| `Invalid service for this center.` | Same for service |
| `A room is required for in-person appointments.` | Slots without room path |
| `room_id is required for in-person appointments.` | in_person missing room |
| `equipment_id is required when the selected room has bookable equipment.` | Room has ≥1 bookable unit |
| `care_team_id cannot be combined with doctor_id or specialty_id.` | Staff XOR |
| `care_team_id and/or doctor_id/specialty_id is required.` | No staff IDs |
| `At least one associate is required. Send care_team_id and/or doctor_id / specialty_id.` | Resolve produced no associates |
| `specialty_id must hold a live non-doctor role mapped to this service.` | specialty_id has no live non-doctor hat on this service’s role reqs (incl. 0 reqs) |
| `doctor_id matches more than one live doctor role.` | Person has two+ live `"doctor"`-in-name hats |
| `Slot no longer available.` | Overlap / race on book/reschedule |
| `Date cannot be in the past.` | Find Slots past `date`, or book/reschedule `start` before now |
| `Invalid start date. Use YYYY-MM-DD.` | Operations `start` junk |
| `Invalid end date. Use YYYY-MM-DD.` | Operations `end` junk |
| `End date cannot be before start date.` | Operations `end` < `start` |
| `Invalid granularity. Use day, week, or month.` | Operations or calendar junk `granularity` |
| `equipment_id must belong to the selected room.` | Unit not on that room |
| `Idempotency key was already used with a different payload.` | 409 |
| `Cannot perform '…' from status '…'.` | Illegal lifecycle |
| `Invalid status. Use open or resolved.` | Exceptions list |
| `Invalid status. Use confirmed, checked_in, in_progress, completed, cancelled, or no_show.` | Appointment list |
| `Invalid <param>.` | Appointment list junk UUID filter |
| `X-Center-ID must match the center in the URL.` | Availability associate routes |
| Roster / hours `detail.day_errors` | Outside hours / roster conflict |

---

*Canonical FE + availability + scheduling contract. Replaces standalone `docs/scheduling.md` and `docs/availability.md`. Last updated: 2026-09-16.*
