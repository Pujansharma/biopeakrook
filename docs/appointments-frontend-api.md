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

Slots are computed on demand (not pre-stored). Cap **200 slots/day** (`truncated: true` if more). Slots with `start` before request time are omitted (today’s past windows; past dates → empty `slots`).

### Pin vs preferred

| Mode | Body | Server |
|---|---|---|
| **Pin** (from Find Slots) | `associates[]` + `room_id` (in_person) + optional `equipment_id` | Validates that combo is free — does **not** re-pick |
| **Preferred** | `preferred.{room_id,care_team_id,doctor_id,specialty_id}` (**required** for Find Slots; required for book/reschedule unless complete pin) | Resolves staff+room from preferred only — no leftover auto-fill |

- Incomplete pin (associates without `room_id` for in_person) → 400, never silent re-resolve.
- `preferred.care_team_id` **XOR** `doctor_id` / `specialty_id` (doctor + specialty OK together).
- Allowed preferred combos: care_team±room · doctor±room · specialty±room · doctor+specialty±room (room required for in_person; forbidden for virtual).
- **Staff+room source:** preferred only, or pin from Find Slots. No leftover fill from `CenterServiceRoleRequirement` / room-type pool.
- `doctor_id` must hold a live role with `"doctor"` in the name; `specialty_id` must hold a live non-doctor role. Same person both IDs → 400. Same associate cannot appear twice on an appointment.
- Old `health_coach_id` → 400 `"Use specialty_id instead of health_coach_id."`
- If assignment has room-type requirements, preferred/pin room must be active at center and `room_type_ref` in that set (OR).
- Find Slots: preferred required. Book/reschedule: complete pin OR valid preferred.
- Pin validates free; does **not** require exactly one associate per service role.
- Pin + `preferred.care_team_id` stamps care team only when every live team member is in the pin.
- Preferred / pin `care_team_id` with **zero live members** → 400 `"Care team has no live members at this center."`

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

**Purpose:** One calendar day of bookable pinned combos for a customer + service. Past starts (`start` < now) are not returned.

**Body (required)**

| Field | Type | Notes |
|---|---|---|
| `customer_profile_id` | UUID | Active profile assigned to this center |
| `service_id` | UUID | Active service assigned to this center |
| `modality` | `"virtual"` \| `"in_person"` | Not `"both"` |
| `date` | `YYYY-MM-DD` | |

**Body (optional)**

```json
"preferred": {
  "room_id": "uuid",
  "care_team_id": "uuid",
  "doctor_id": "uuid",
  "specialty_id": "uuid"
}
```

Omit empty preferred keys (blank UUID → 400). Never send `care_team_id` with doctor/coach.

**Staff on each slot**

| Center assignment | Preferred staff (`care_team_id` / `doctor_id` / `specialty_id`) | Result |
|---|---|---|
| ≥1 active role requirement | omit OK | Auto-pick free associate per role |
| ≥1 active role requirement | set | Prefer fills / biases role pools (+ extras) |
| 0 role requirements | set | Staff from care team / preferred people as extras |
| 0 role requirements | omit (room-only or none) | No slots (soft-skip) — configure roles or send preferred staff |

`preferred.room_id` alone is fine when the service has role requirements (normal in_person path).

**Example payloads**

```json
{
  "customer_profile_id": "…",
  "service_id": "…",
  "modality": "in_person",
  "date": "2026-09-05",
  "preferred": { "room_id": "…" }
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
      "associates": [
        { "role_id": "uuid", "associate_id": "uuid" }
      ],
      "room_id": "uuid",
      "equipment_id": null
    }
  ]
}
```

Each slot = one pinned combo. Pass that pin into book.

**Common 400:** invalid customer/service for center · modality not supported · room required for in_person · care_team XOR people · service duration missing · no staff path (zero role requirements and no preferred `care_team_id` / `doctor_id` / `specialty_id`).

---

### POST `…/` — Book

**Purpose:** Create confirmed appointment.

**Headers:** optional `Idempotency-Key` (UUID). Same key + same payload → 200 existing detail. Same key + different payload → **409**.

**Body**

| Field | Required | Notes |
|---|---|---|
| `customer_profile_id` | yes | |
| `service_id` | yes | |
| `modality` | yes | `virtual` \| `in_person` |
| `start` | yes | ISO datetime (from slot) |
| `end` | yes | ISO datetime (from slot) |
| `associates` | pin path | `[{role_id, associate_id}, …]` |
| `room_id` | pin + in_person | |
| `equipment_id` | optional | null OK |
| `preferred` | preferred path | same shape as slots |

**Pinned book example**

```json
{
  "customer_profile_id": "…",
  "service_id": "…",
  "modality": "in_person",
  "start": "2026-09-05T04:00:00Z",
  "end": "2026-09-05T04:40:00Z",
  "associates": [{ "role_id": "…", "associate_id": "…" }],
  "room_id": "…",
  "equipment_id": null
}
```

**Response:** 201 `data` = appointment detail. Idempotent replay: 200 same shape.

**Common 400:** pin incomplete · slot no longer available · invalid room/equipment · no staff path (zero roles + no preferred staff) · need preferred or pin when roles required.

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

Reschedule lands `confirmed`. Same pin/preferred rules as book. Overlap → `"Slot no longer available."`

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
| `start` | `YYYY-MM-DD` (default today UTC date) |
| `end` | optional end date; if omitted use `granularity` |
| `granularity` | default `week` — used when `end` omitted |

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

1. **Book:** Find Slots → pick slot → Book with that pin (+ optional Idempotency-Key).
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
| `Pin requires room_id for in-person appointments.` | Incomplete pin |
| `care_team_id cannot be combined with doctor_id or specialty_id.` | Preferred XOR |
| `Send preferred resources or a pinned associates list.` | Roles required, neither path |
| `At least one associate is required. Send a pin or preferred care_team_id / doctor_id / specialty_id.` | Misconfig: zero service role requirements and no preferred staff (not the normal roles / pin path) |
| `Slot no longer available.` | Overlap / race on book/reschedule |
| `Invalid room/equipment for this center.` | Bad pin IDs |
| `Idempotency key was already used with a different payload.` | 409 |
| `Cannot perform '…' from status '…'.` | Illegal lifecycle |
| `Invalid status. Use open or resolved.` | Exceptions list |
| `Invalid status. Use confirmed, checked_in, in_progress, completed, cancelled, or no_show.` | Appointment list |
| `Invalid <param>.` | Appointment list junk UUID filter |
| `X-Center-ID must match the center in the URL.` | Availability associate routes |
| Roster / hours `detail.day_errors` | Outside hours / roster conflict |

---

*Canonical FE + availability + scheduling contract. Replaces standalone `docs/scheduling.md` and `docs/availability.md`. Last updated: 2026-09-05.*
