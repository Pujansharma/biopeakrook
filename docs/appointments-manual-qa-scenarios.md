# Test the appointment system manually

This document helps Quality Assurance (QA) testers test appointment setup, slot search, booking, lifecycle actions, availability, exceptions, care teams, operations, and notifications. Follow each scenario and compare the actual API status, response, and saved data with the expected result.

## 1. How to use this document

Run P0 scenarios first. A failed P0 scenario blocks the main appointment flow.

- **P0**: Main flow or critical data protection
- **P1**: Important validation or business rule
- **P2**: Reporting, unusual input, or operational edge case

For each test:

1. Record test data IDs and the local date and time.
2. Send the request from Bruno or another API client.
3. Record the HTTP status.
4. Check `detail` and `data`.
5. Use a follow-up GET request to confirm saved data.
6. Check database or worker data only when access is available.
7. Save evidence for every failure.

Unless a scenario says otherwise, use:

- Active staff access token
- Active center
- Active customer assigned to that center
- Active service assigned to that center
- Future date in the center timezone

## 2. Common API checks

### Successful response

Expected shape:

```json
{
  "detail": "Human-readable message",
  "data": {}
}
```

`data` may be an object or list. Some successful responses omit `data`.

### Field validation error

Expected status: `400`

```json
{
  "detail": {
    "field_name": [
      "Validation message"
    ]
  }
}
```

### Plain validation error

Expected status: `400`

```json
{
  "detail": "Validation message"
}
```

### General checks for every endpoint

- Response is valid JSON
- Response does not contain a top-level `success` field
- UUID values use valid UUID format
- Date and time values use ISO 8601 format
- Wrong-center records are not exposed
- Secret tokens do not appear in responses or logs
- Validation failure does not create or change data

## 3. Prepare test data

Create or identify this data before testing.

### Centers and users

- Center A: active, timezone configured
- Center B: active
- Admin user without center assignments
- Associate A1: active assignment to Center A
- Associate A2: active assignment to Center A
- Associate B1: active assignment to Center B only
- Inactive associate
- Customer C1: active profile assigned to Center A
- Customer C2: active profile assigned to Center B only
- Customer C3: active profile assigned to Center A and Center B
- Inactive customer profile

### Services and roles

- Service S1: active at Center A, virtual and in-person allowed
- Service S1 duration: known value, for example 40 minutes
- Service S1 buffers: known values, for example 10 minutes before and after
- Service S2: active at Center B only
- Service S3: active at Center A with no configured duration
- Service S4: active at Center A but not available for virtual appointments
- Doctor role
- Non-doctor specialty role mapped to Service S1
- Non-doctor role not mapped to Service S1
- Inactive role
- Associate A1 with one live doctor role
- Associate A2 with one live specialty role mapped to Service S1

### Availability and resources

- Center A operating hours cover the test date
- A1 and A2 roster covers the test time
- Room R1: active, active room type, valid for Service S1
- Room R2: active, valid room type, no bookable equipment
- Room R3: active, room type not mapped to Service S1
- Equipment E1: active, active type, assigned to R1
- Equipment E2: active, active type, assigned to another room
- Care Team T1: active, A1 and A2 are live members
- Care Team T2: active, no live members

Keep one open time window with no appointments, blocks, leaves, closures, or downtime.

## 4. Authentication and center access

### AUTH-01: Valid associate accesses own center

- **Priority**: P0
- **Request**: Call a Center A appointment endpoint with A1 token
- **Expected status**: `200`, or the normal success status for that endpoint
- **Expected data**: Center A data only

### AUTH-02: Associate accesses another center

- **Priority**: P0
- **Request**: Call a Center B endpoint with A1 token
- **Expected status**: `403`
- **Expected data**: No Center B records

### AUTH-03: Request has no access token

- **Priority**: P0
- **Request**: Call any protected appointment endpoint without `Authorization`
- **Expected status**: `401`
- **Expected data**: No data changes

### AUTH-04: Request has an invalid or expired token

- **Priority**: P0
- **Expected status**: `401`
- **Expected data**: No data changes

### AUTH-05: Customer token calls staff endpoint

- **Priority**: P0
- **Expected status**: `403`
- **Expected data**: No appointment data

### AUTH-06: Wrong-center appointment ID

- **Priority**: P0
- **Request**: Use a Center B appointment ID in a Center A detail or action URL
- **Expected status**: `404`
- **Expected detail**: `Appointment not found.`

### AUTH-07: Availability center header matches URL

- **Priority**: P0
- **Request**: Call a Center A availability endpoint as A1 with `X-Center-ID: <center_a_id>`
- **Expected status**: `200`

### AUTH-08: Availability center header does not match URL

- **Priority**: P0
- **Request**: Call a Center A availability endpoint with `X-Center-ID: <center_b_id>`
- **Expected status**: `400`
- **Expected detail**: `X-Center-ID must match the center in the URL.`

## 5. Find appointment slots

Endpoint:

```text
POST /centers/<center_id>/appointments/slots/
```

### Base virtual request

```json
{
  "customer_profile_id": "customer_profile_uuid",
  "service_id": "service_uuid",
  "modality": "virtual",
  "date": "future_yyyy_mm_dd",
  "preferred": {
    "specialty_id": "associate_uuid"
  }
}
```

### Base in-person request

```json
{
  "customer_profile_id": "customer_profile_uuid",
  "service_id": "service_uuid",
  "modality": "in_person",
  "date": "future_yyyy_mm_dd",
  "preferred": {
    "specialty_id": "associate_uuid",
    "room_id": "room_uuid",
    "equipment_id": "equipment_uuid"
  }
}
```

### SLOT-01: Find virtual slots with specialty

- **Priority**: P0
- **Setup**: A2 and customer are free
- **Request**: Send base virtual request with A2
- **Expected status**: `200`
- **Expected detail**: `Appointment slots retrieved.`
- **Expected data**:
  - Correct date, timezone, duration, and buffers
  - `slots` is a list
  - Each slot has `start`, `end`, and nested `specialty`
  - `specialty.role` matches the mapped Service S1 role
  - No `room`, `equipment`, `care_team`, or raw resource ID fields

### SLOT-02: Find virtual slots with doctor

- **Priority**: P0
- **Request**: Send `preferred.doctor_id` with A1
- **Expected status**: `200`
- **Expected data**: Each slot has nested `doctor`

### SLOT-03: Find slots with doctor and specialty

- **Priority**: P0
- **Request**: Send A1 as doctor and A2 as specialty
- **Expected status**: `200`
- **Expected data**: Each slot contains both nested people

### SLOT-04: Find slots with care team

- **Priority**: P0
- **Request**: Send `preferred.care_team_id` with T1
- **Expected status**: `200`
- **Expected data**: Each slot has nested `care_team`
- **Expected data**: Slot does not expose a raw `associates` list

### SLOT-05: Find in-person slots with required equipment

- **Priority**: P0
- **Request**: Use R1 and E1
- **Expected status**: `200`
- **Expected data**: Each slot has matching nested room and equipment

### SLOT-06: Find in-person slots where room has no equipment

- **Priority**: P0
- **Request**: Use R2 and omit `equipment_id`
- **Expected status**: `200`
- **Expected data**: Slots have room and no equipment

### SLOT-07: No free time

- **Priority**: P0
- **Setup**: Block the full available window
- **Expected status**: `200`
- **Expected data**: `slots` is empty
- **Expected data**: This is not an API error

### SLOT-08: Past date

- **Priority**: P0
- **Request**: Use yesterday in the center timezone
- **Expected status**: `400`
- **Expected detail**: `Date cannot be in the past.`

### SLOT-09: Today removes elapsed starts

- **Priority**: P1
- **Request**: Use today
- **Expected status**: `200`
- **Expected data**: Every returned slot starts at or after the request time

### SLOT-10: Missing preferred object

- **Priority**: P0
- **Expected status**: `400`
- **Expected detail**: `preferred` contains `This field is required.`

### SLOT-11: Empty preferred object

- **Priority**: P0
- **Request**: Send `"preferred": {}`
- **Expected status**: `400`
- **Expected detail**: `preferred` contains `preferred is required.`

### SLOT-12: Care team mixed with person IDs

- **Priority**: P0
- **Request**: Send `care_team_id` with `doctor_id` or `specialty_id`
- **Expected status**: `400`
- **Expected detail**: `care_team_id cannot be combined with doctor_id or specialty_id.`

### SLOT-13: Same person is doctor and specialty

- **Priority**: P1
- **Expected status**: `400`
- **Expected data**: No slots returned

### SLOT-14: Old health coach field

- **Priority**: P1
- **Request**: Send `health_coach_id`
- **Expected status**: `400`
- **Expected detail**: `Use specialty_id instead of health_coach_id.`

### SLOT-15: Unsupported modality

- **Priority**: P0
- **Request**: Send `"modality": "both"`
- **Expected status**: `400`
- **Expected detail**: `Modality must be virtual or in_person.`

### SLOT-16: In-person request without room

- **Priority**: P0
- **Expected status**: `400`
- **Expected error**: Room is required

### SLOT-17: Virtual request with room or equipment

- **Priority**: P1
- **Expected status**: `400`
- **Expected data**: No slots returned

### SLOT-18: Room has equipment but request omits equipment

- **Priority**: P0
- **Request**: Use R1 without `equipment_id`
- **Expected status**: `400`
- **Expected detail**: `equipment_id is required when the selected room has bookable equipment.`

### SLOT-19: Room has no equipment but request sends equipment

- **Priority**: P1
- **Request**: Use R2 with any equipment ID
- **Expected status**: `400`

### SLOT-20: Equipment belongs to another room

- **Priority**: P0
- **Request**: Use R1 with E2
- **Expected status**: `400`
- **Expected detail**: `equipment_id must belong to the selected room.`

### SLOT-21: Invalid customer for center

- **Priority**: P0
- **Test values**: C2, inactive customer, and random UUID
- **Expected status**: `400`
- **Expected detail**: `Invalid customer profile for this center.`

### SLOT-22: Invalid service for center

- **Priority**: P0
- **Test values**: S2, inactive assignment, and random UUID
- **Expected status**: `400`
- **Expected detail**: `Invalid service for this center.`

### SLOT-23: Service duration is missing

- **Priority**: P0
- **Request**: Use S3
- **Expected status**: `400`
- **Expected detail**: `Service duration is not configured for this center.`

### SLOT-24: Service does not support modality

- **Priority**: P0
- **Request**: Use S4 with `virtual`
- **Expected status**: `400`
- **Expected detail**: `Modality is not supported for this service.`

### SLOT-25: Invalid room eligibility

- **Priority**: P0
- **Test values**:
  - Inactive room
  - Room from Center B
  - Room without a room type
  - Room with an inactive room type
  - R3, whose room type is not mapped to S1
- **Expected status**: `400`
- **Expected data**: No slots returned

### SLOT-26: Invalid specialty

- **Priority**: P0
- **Test values**: Wrong-center associate, inactive associate, unmapped role, inactive role link
- **Expected status**: `400`
- **Expected detail**: `specialty_id must hold a live non-doctor role mapped to this service.`

### SLOT-27: Invalid doctor role count

- **Priority**: P1
- **Test values**: Associate with no doctor role, then associate with two live doctor roles
- **Expected status**: `400`
- **Expected data**: No slots returned

### SLOT-28: Care team has no live members

- **Priority**: P0
- **Request**: Use T2
- **Expected status**: `400`
- **Expected detail**: `Care team has no live members at this center.`

### SLOT-29: Availability subtractors

- **Priority**: P0
- **Setup**: In each run, overlap the candidate slot's exclusive range and target its selected associate, care team, room, or equipment
- **Repeat with**:
  - Center closure
  - Associate block
  - Associate leave
  - Care team block
  - Room block
  - Room downtime
  - Equipment block
  - Equipment downtime
  - Existing busy appointment
- **Expected result**: Returned slots do not overlap the blocked exclusive range

### SLOT-30: Customer is busy at another center

- **Priority**: P0
- **Setup**: Give C3 a busy appointment at Center B using valid Center B service, staff, hours, and roster
- **Expected result**: Center A does not return overlapping slots

### SLOT-31: Boundary adjacency

- **Priority**: P1
- **Setup**: Existing busy exclusive range ends at 11:00
- **Expected result**: A new exclusive range may start at 11:00

### SLOT-32: Slot limit

- **Priority**: P2
- **Setup**: Configure enough availability to produce more than 200 slots
- **Expected status**: `200`
- **Expected data**: At most 200 slots and `truncated: true`

## 6. Book an appointment

Endpoint:

```text
POST /centers/<center_id>/appointments/
```

Use `start` and `end` from Find Slots. Move nested slot IDs to top-level booking fields.

### Base booking request

```json
{
  "customer_profile_id": "customer_profile_uuid",
  "service_id": "service_uuid",
  "modality": "in_person",
  "start": "slot_start_iso",
  "end": "slot_end_iso",
  "specialty_id": "associate_uuid",
  "room_id": "room_uuid",
  "equipment_id": "equipment_uuid",
  "notes": "Manual QA booking"
}
```

### BOOK-01: Book a returned slot

- **Priority**: P0
- **Expected status**: `201`
- **Expected detail**: `Appointment booked.`
- **Expected data**:
  - New appointment ID and code
  - Status is `confirmed`
  - Request times, modality, customer, service, room, and equipment match
  - `associates` contains selected staff and stamped roles
  - `duration_minutes` and buffers match Service S1 assignment
  - `exclusive_start` and `exclusive_end` include buffers
  - Notes match request
- **Follow-up**: Detail and list endpoints return the appointment

### BOOK-02: Book a virtual appointment

- **Priority**: P0
- **Request**: Use doctor, specialty, or both; omit room and equipment
- **Expected status**: `201`
- **Expected data**: Room and equipment are `null`

### BOOK-03: Book with a care team

- **Priority**: P0
- **Request**: Send `care_team_id` and no person IDs
- **Expected status**: `201`
- **Expected data**: Care team matches T1 and live members appear in `associates`

### BOOK-04: Book with no notes

- **Priority**: P1
- **Expected status**: `201`
- **Expected data**: Notes are `null`

### BOOK-05: End does not match service duration

- **Priority**: P0
- **Request**: Change `end` by one minute
- **Expected status**: `400`
- **Expected detail**: `Appointment end time does not match configured duration.`
- **Expected data**: No appointment created

### BOOK-06: Slot became unavailable

- **Priority**: P0
- **Setup**: Find a slot, then book a conflicting appointment before using it
- **Expected status**: `400`
- **Expected detail**: `Slot no longer available.`

### BOOK-07: Customer overlap

- **Priority**: P0
- **Setup**: Customer already has an overlapping busy appointment
- **Expected status**: `400`
- **Expected data**: Second appointment is not created

### BOOK-08: Resource overlap uses buffers

- **Priority**: P0
- **Setup**: Session times do not overlap, but exclusive ranges overlap
- **Expected status**: `400`
- **Expected data**: Second appointment is not created

### BOOK-09: Invalid booking fields

- **Priority**: P0
- **Repeat**: All invalid staff, room, equipment, customer, service, and modality cases from slot search
- **Expected status**: `400`
- **Expected data**: No appointment, staff link, audit, or notification row

### BOOK-10: Same idempotency key and same body

- **Priority**: P0
- **Header**: `Idempotency-Key: 12345678-1234-4123-8123-123456789012`
- **Steps**: Send the same valid request twice
- **Expected first status**: `201`
- **Expected second status**: `200`
- **Expected second detail**: `Appointment retrieved.`
- **Expected data**: Same appointment ID; only one appointment exists
- **Defect rule**: If replay returns a slot conflict, file a defect

### BOOK-11: Same idempotency key and different body

- **Priority**: P0
- **Steps**: Reuse the key with a changed payload
- **Expected status**: `409`
- **Expected detail**: `Idempotency key was already used with a different payload.`
- **Expected data**: No second appointment

### BOOK-12: Same idempotency key at another center

- **Priority**: P1
- **Expected result**: Key is scoped to the center and does not return Center A data at Center B

### BOOK-13: Notification failure does not undo booking

- **Priority**: P0
- **Setup**: Disable or break notification configuration in a safe environment
- **Expected status**: `201`
- **Expected data**: Appointment remains saved
- **Expected side effect**: Notification work is skipped or failed separately

### BOOK-14: Direct booking in the past

- **Priority**: P0
- **Request**: Send valid historical times without using Find Slots
- **Expected status**: `400`
- **Expected data**: No historical appointment is created
- **Defect rule**: File a defect if booking succeeds

## 7. List and view appointments

### LIST-01: Default appointment list

- **Priority**: P0
- **Request**: `GET /centers/<center_id>/appointments/`
- **Expected status**: `200`
- **Expected detail**: `Appointments retrieved.`
- **Expected data**: Current week, chronological order, Center A records only

### LIST-02: Day, week, and month windows

- **Priority**: P0
- **Request**: Use `start` with each `granularity`
- **Expected result**:
  - Day returns appointments overlapping that day
  - Week uses Monday through Sunday
  - Month uses the calendar month

### LIST-03: Search without start

- **Priority**: P1
- **Request**: Search by customer name, email, phone, appointment code, and service name
- **Expected data**: Matches from all dates, newest first

### LIST-04: Search with start

- **Priority**: P1
- **Expected data**: Search stays inside the requested date window

### LIST-05: Filter each supported field

- **Priority**: P1
- **Filters**:
  - `associate_id`
  - `role_id`
  - `service_id`
  - `room_id`
  - `equipment_id`
  - `equipment_type_id`
  - `status`
  - `care_team_id`
- **Expected data**: Every returned row matches the filter

### LIST-06: Associate and role filters together

- **Priority**: P1
- **Request**: Send both filters
- **Expected data**: Appointment matches the associate or the role

### LIST-07: Invalid filters

- **Priority**: P1
- **Request**: Send junk UUID values and unsupported status or granularity
- **Expected status**: `400`
- **Expected data**: Error names the invalid field

### LIST-08: Empty result

- **Priority**: P1
- **Expected status**: `200`
- **Expected data**: Empty appointments list, `total_count: 0`, `truncated: false`

### LIST-09: Result limit

- **Priority**: P2
- **Setup**: Create more than 500 matching rows for week, month, or unscoped search
- **Expected data**: At most 500 rows and `truncated: true`

### DETAIL-01: View appointment

- **Priority**: P0
- **Request**: `GET /centers/<center_id>/appointments/<appointment_id>/`
- **Expected status**: `200`
- **Expected detail**: `Appointment retrieved.`
- **Expected data**: Full appointment, notes, buffers, exclusive times, exception state, and Google Meet link

### DETAIL-02: Missing appointment

- **Priority**: P0
- **Expected status**: `404`
- **Expected detail**: `Appointment not found.`

## 8. Appointment lifecycle

### LIFE-01: Complete normal visit flow

- **Priority**: P0
- **Steps**:
  1. Book appointment and confirm status `confirmed`
  2. POST `check-in/` and confirm `checked_in`
  3. POST `start/` and confirm `in_progress`
  4. POST `mark-late/` with `{"late_by": 10}`
  5. POST `complete/` and confirm `completed`
- **Expected result**: Every action returns `200` and full appointment data
- **Expected data**: Late flag and minutes remain visible after completion

### LIFE-02: Mark no-show

- **Priority**: P0
- **Setup**: Appointment is `confirmed`
- **Request**: POST `no-show/`
- **Expected status**: `200`
- **Expected data**: Status is `no_show`; slot becomes available

### LIFE-03: Cancel confirmed appointment

- **Priority**: P0
- **Request body**:

```json
{
  "reason": "Customer requested cancellation"
}
```

- **Expected status**: `200`
- **Expected data**: Status is `cancelled`; reason is saved; slot becomes available

### LIFE-04: Cancel checked-in appointment

- **Priority**: P0
- **Expected status**: `200`
- **Expected data**: Status is `cancelled`

### LIFE-05: Reschedule confirmed appointment

- **Priority**: P0
- **Request**: Send full booking body with a newly returned slot
- **Expected status**: `200`
- **Expected data**:
  - Status is `confirmed`
  - New times and resources are saved
  - Customer and service remain unchanged
  - Late fields reset
  - Old slot becomes available

### LIFE-06: Reschedule checked-in appointment

- **Priority**: P0
- **Expected status**: `200`
- **Expected data**: Status returns to `confirmed`

### LIFE-07: Reschedule notes behavior

- **Priority**: P1
- **Repeat**:
  - Omit notes: old notes remain
  - Send `null`: old notes remain
  - Send empty string: notes clear
  - Send new text: notes update

### LIFE-08: Change customer during reschedule

- **Priority**: P0
- **Expected status**: `400`
- **Expected data**: Original appointment does not change

### LIFE-09: Change service during reschedule

- **Priority**: P0
- **Expected status**: `400`
- **Expected data**: Original appointment does not change

### LIFE-10: Illegal transitions

- **Priority**: P0
- **Test examples**:
  - Start from `confirmed`
  - Complete from `checked_in`
  - Cancel from `in_progress`
  - Reschedule from `in_progress`
  - No-show from `checked_in`
  - Repeat any completed action
- **Expected status**: `400`
- **Expected detail**: `Cannot perform '<action>' from status '<status>'.`
- **Expected data**: Status and timestamps do not change

### LIFE-11: Invalid late minutes

- **Priority**: P1
- **Test values**: Missing, zero, negative, text
- **Expected status**: `400`
- **Expected data**: Appointment remains unchanged

### LIFE-12: Invalid cancellation reason

- **Priority**: P1
- **Test values**: Missing reason and more than 500 characters
- **Expected status**: `400`
- **Expected data**: Appointment remains unchanged

### LIFE-13: Lifecycle audit

- **Priority**: P1
- **Expected side effect**: Each successful action creates one audit entry
- **Expected side effect**: Failed actions create no audit entry

## 9. Appointment exceptions

### EXC-01: Create exception for each blocker

- **Priority**: P0
- **Setup**: Create a busy appointment first
- **Repeat with**:
  - Associate leave
  - Associate block
  - Roster change
  - Care team block
  - Room block
  - Equipment block
  - Room downtime
  - Equipment downtime
  - Center closure
- **Expected result**: One open exception links the appointment and blocker
- **Expected appointment data**: `has_open_exception: true`
- **Worker note**: One-off blockers are checked immediately. For roster changes and recurring blockers, run `uv run manage.py process_appointment_exception_scans` before checking.

### EXC-02: Non-overlapping blocker

- **Priority**: P1
- **Expected result**: No exception

### EXC-03: Duplicate scan

- **Priority**: P1
- **Steps**: Run the same scan twice
- **Expected result**: Only one open exception for that appointment and source

### EXC-04: List open and resolved exceptions

- **Priority**: P0
- **Requests**: GET with `status=open`, then `status=resolved`
- **Expected data**: Correct records and pagination fields

### EXC-05: Exception count

- **Priority**: P0
- **Request**: GET `exceptions/count/`
- **Expected data**: `open_count` matches open exception list

### EXC-06: Invalid exception status

- **Priority**: P1
- **Expected status**: `400`
- **Expected detail**: `Invalid status. Use open or resolved.`

### EXC-07: Acknowledge exception

- **Priority**: P0
- **Request**: POST `exceptions/<exception_id>/acknowledge/`
- **Expected status**: `200`
- **Expected detail**: `Exception acknowledged.`
- **Expected data**: Exception is resolved; appointment status does not change

### EXC-08: Appointment has multiple exceptions

- **Priority**: P0
- **Steps**: Resolve only one exception
- **Expected data**: `has_open_exception` stays true until all exceptions resolve

### EXC-09: Cancel appointment with open exception

- **Priority**: P0
- **Expected result**: Exception resolution is `cancelled`

### EXC-10: Reschedule appointment with open exception

- **Priority**: P0
- **Expected result**: Old exception resolution is `rescheduled`

### EXC-11: Deactivate blocker

- **Priority**: P1
- **Expected result**: Related open exception resolves as `blocker_cleared`

### EXC-12: Async scan

- **Priority**: P1
- **Setup**: Create recurring block or change roster
- **Expected API data**: `exception_scan: "queued"`
- **Worker action**: Run `uv run manage.py process_appointment_exception_scans`
- **Expected result**: Matching exceptions appear after the worker completes

### EXC-13: Care team block scope

- **Priority**: P1
- **Setup**: Create one team appointment and one solo appointment for a team member
- **Expected result**: Team block creates an exception only for the team appointment

## 10. Care teams

### TEAM-01: Create care team

- **Priority**: P0
- **Request**: Use two live associates with two unique active roles
- **Expected status**: `201`
- **Expected detail**: `Care team created.`
- **Expected data**: Name, active state, members, and count match request

### TEAM-02: Fewer than two members

- **Priority**: P0
- **Expected status**: `400`
- **Expected data**: Team is not created

### TEAM-03: Duplicate associate or role

- **Priority**: P1
- **Expected status**: `400`

### TEAM-04: Invalid member role

- **Priority**: P0
- **Test values**: Inactive role, other-center role, role not linked to associate
- **Expected status**: `400`
- **Expected data**: Team is not created

### TEAM-05: Duplicate name with different letter case

- **Priority**: P1
- **Expected status**: `400`

### TEAM-06: Replace members

- **Priority**: P0
- **Request**: PATCH with a complete new members list
- **Expected status**: `200`
- **Expected data**: Old members are removed; new members appear

### TEAM-07: List active and inactive teams

- **Priority**: P1
- **Request**: Omit `active`, then use `active=1` and `active=0`
- **Expected data**: Omitted filter returns both states

### TEAM-08: Filter by live members

- **Priority**: P1
- **Request**: Use `members_live=1` and `members_live=0`
- **Expected data**: Teams match member user, assignment, role-link, and role state

### TEAM-09: Deactivate and reactivate team

- **Priority**: P1
- **Expected result**:
  - Deactivation also deactivates active team blocks
  - Open exceptions from those blocks resolve
  - Reactivation does not restore those blocks
- **Defect rule**: File a defect if block exceptions remain open

## 11. Availability calendars

### CAL-01: Center calendar

- **Priority**: P0
- **Request**: GET `/availability/`
- **Expected data**: Correct timezone, date range, base windows, available windows, and events

### CAL-02: Associate calendar

- **Priority**: P0
- **Expected data**: Base windows equal center hours intersected with roster
- **Expected data**: Personal blocks, leave, team blocks, closures, and busy appointments subtract time

### CAL-03: Care team calendar

- **Priority**: P0
- **Expected data**: Base windows equal the intersection of live member calendars
- **Expected data**: Team and member events include source IDs

### CAL-04: Room calendar

- **Priority**: P0
- **Expected data**: Blocks, downtime, closures, and busy appointments subtract time

### CAL-05: Equipment calendar

- **Priority**: P0
- **Expected data**: Blocks, downtime, closures, and busy appointments subtract time

### CAL-06: Calendar granularity

- **Priority**: P1
- **Expected defaults**: Center uses week; other resources use day
- **Repeat**: Day, week, and month return correct date boundaries

### CAL-07: Non-busy statuses

- **Priority**: P0
- **Setup**: Complete, cancel, or mark no-show
- **Expected result**: Appointment no longer removes calendar availability

## 12. Operating hours and roster

### HOURS-01: Set center hours

- **Priority**: P0
- **Request**: PATCH open and closed weekdays
- **Expected status**: `200`
- **Expected data**: Only requested weekdays change

### HOURS-02: Invalid hours

- **Priority**: P0
- **Test values**: Missing times, close before open, same day in open and closed lists
- **Expected status**: `400`
- **Expected data**: No hours change

### HOURS-03: Shrink hours around active roster

- **Priority**: P0
- **Expected status**: `400`
- **Expected data**: `day_errors` explains each conflict
- **Expected data**: No hours change

### ROSTER-01: Add roster days

- **Priority**: P0
- **Request**: POST non-empty entries inside center hours
- **Expected status**: `201`
- **Expected data**: Requested days are active
- **Expected sibling field**: `exception_scan: "queued"`

### ROSTER-02: Replace roster week

- **Priority**: P0
- **Request**: PATCH a subset of active days
- **Expected result**: Omitted active days become inactive

### ROSTER-03: Roster boundary matches center hours

- **Priority**: P1
- **Expected status**: Success

### ROSTER-04: Roster outside center hours

- **Priority**: P0
- **Expected status**: `400`
- **Expected error code**: `before_opening` or `after_closing`

### ROSTER-05: Roster on closed or missing-hours day

- **Priority**: P0
- **Expected status**: `400`
- **Expected error code**: `center_closed` or `center_hours_missing`

### ROSTER-06: Empty or duplicate roster entries

- **Priority**: P1
- **Expected status**: `400`

## 13. Blocks, leave, downtime, and closures

Run relevant cases for associate, care team, room, and equipment endpoints.

### UNAV-01: Create one-off block

- **Priority**: P0
- **Expected status**: `201`
- **Expected data**: List containing the created row
- **Expected result**: Calendar and slot search remove that time

### UNAV-02: Create recurring block

- **Priority**: P0
- **Request**: Send multiple weekday values
- **Expected data**: One created row per weekday

### UNAV-03: Overlapping active block

- **Priority**: P0
- **Expected status**: `400`
- **Expected detail**: `Overlaps an existing unavailability window.`

### UNAV-04: Adjacent blocks

- **Priority**: P1
- **Setup**: First block ends when second starts
- **Expected result**: Both blocks are accepted

### UNAV-05: Associate leave overlaps block

- **Priority**: P1
- **Steps**: Create block, then create leave over it
- **Expected result**: Leave is accepted

### UNAV-06: Associate block overlaps leave

- **Priority**: P1
- **Steps**: Create leave, then create block over it
- **Expected status**: `400`

### UNAV-07: Downtime overlaps block

- **Priority**: P1
- **Steps**: Create block, then downtime over it
- **Expected result**: Downtime is accepted

### UNAV-08: Block overlaps downtime

- **Priority**: P1
- **Steps**: Create downtime, then block over it
- **Expected status**: `400`

### UNAV-09: Overlapping downtime

- **Priority**: P0
- **Expected status**: `400`

### UNAV-10: Cross-midnight room or equipment window

- **Priority**: P1
- **Expected status**: `400`
- **Expected detail**: `Must be after start_time on the same day.`

### UNAV-11: Unsupported effective-until field

- **Priority**: P2
- **Expected status**: `400`
- **Expected detail**: `Not supported. Deactivate the block with is_active=false.`

### UNAV-12: All-center leave

- **Priority**: P0
- **Request**: Send `"scope": "all_centers"`
- **Expected data**: Stored center is null
- **Expected result**: Leave affects every assigned-center calendar and slot search

### UNAV-13: Create closure

- **Priority**: P0
- **Expected status**: `201`
- **Expected result**: Entire local date becomes unavailable

### UNAV-14: Duplicate active closure date

- **Priority**: P1
- **Expected status**: `400`

### UNAV-15: Recreate inactive closure date

- **Priority**: P1
- **Expected result**: Existing closure becomes active again

### UNAV-16: Soft-deactivate unavailability

- **Priority**: P0
- **Request**: PATCH `{"is_active": false}`
- **Expected result**: Time becomes available again
- **Expected result**: Related open exception resolves when supported

### UNAV-17: Active list filter

- **Priority**: P1
- **Requests**: Omit `active`, then use `active=1` and `active=0`
- **Expected result**: Omitted filter returns active rows; explicit filters return matching rows

### UNAV-18: Change an active blocker

- **Priority**: P1
- **Request**: PATCH the blocker to a different date or time
- **Expected result**: Old linked exceptions resolve and new conflicts create exceptions
- **Defect rule**: File a defect if exception data remains stale

## 14. Operations dashboards

Endpoints:

```text
GET /operations/overview/
GET /operations/staff/
GET /operations/rooms/
GET /operations/equipment/
GET /operations/capacity/
GET /operations/bottlenecks/
```

### OPS-01: Empty date range

- **Priority**: P1
- **Expected status**: `200`
- **Expected data**: Zero counts and empty breakdowns; no divide-by-zero error

### OPS-02: Overview totals

- **Priority**: P1
- **Setup**: Create appointments with known services and times
- **Expected data**: Appointment count, booked minutes, hours, status breakdown, service breakdown, and peak hours match source data

### OPS-03: Resource utilization

- **Priority**: P1
- **Expected data**:
  - Available minutes reflect hours, roster, closures, blocks, leave, and downtime
  - Booked minutes reflect appointments
  - Hours round to two decimals
  - Utilization rounds to four decimals

### OPS-04: Capacity totals

- **Priority**: P1
- **Expected data**: Staff, room, and equipment totals equal corresponding detail endpoints

### OPS-05: Underused staff bottleneck

- **Priority**: P2
- **Setup**: Staff has availability and utilization below 0.2
- **Expected data**: Staff appears as `staff_underutilized`

### OPS-06: Downtime bottleneck

- **Priority**: P2
- **Setup**: Downtime overlaps an appointment
- **Expected data**: Resource, time, reason, and dependent count are correct

### OPS-07: Cache invalidation

- **Priority**: P1
- **Steps**: Read dashboard, book or change appointment, read dashboard again
- **Expected result**: New values appear without waiting 10 minutes

### OPS-08: Invalid range values

- **Priority**: P1
- **Test values**: Invalid dates, unsupported granularity, end before start
- **Expected status**: `400`
- **Expected data**: No server error
- **Defect rule**: File a defect for `500`, silent fallback, or reversed range acceptance

### OPS-09: Busy-status counting

- **Priority**: P1
- **Steps**: Compare metrics before and after cancel, no-show, and complete
- **Expected result**: Completed appointments remain counted as delivered work
- **Expected result**: Cancelled and no-show appointments do not count as booked capacity
- **Defect rule**: File a defect if cancelled or no-show rows remain counted

## 15. Notifications and Google Calendar

Booking, rescheduling, and cancellation queue notification work after the appointment saves.

### COMMS-01: Booking queues notifications

- **Priority**: P1
- **Expected API result**: Booking succeeds before external delivery
- **Expected side effect**: WhatsApp and Google Calendar work is pending, skipped, or processed

### COMMS-02: Reschedule queues updated details

- **Priority**: P1
- **Expected side effect**: Message and calendar event use new date, time, room, modality, and staff

### COMMS-03: Cancellation queues cancellation

- **Priority**: P1
- **Expected side effect**: WhatsApp cancellation is queued; Google event deletion is queued
- **Expected appointment data**: Existing Google event and Meet IDs remain stored

### COMMS-04: Other lifecycle actions

- **Priority**: P2
- **Actions**: Check-in, start, mark-late, complete, no-show, acknowledge exception
- **Expected side effect**: No booking, reschedule, or cancellation message is queued

### COMMS-05: Missing phone or provider settings

- **Priority**: P1
- **Expected result**: Appointment action succeeds
- **Expected side effect**: Notification row is skipped or failed with a useful reason

### COMMS-06: Virtual appointment Google Meet

- **Priority**: P1
- **Expected result**: Worker creates or updates a calendar event with Meet details
- **Expected API behavior**: Meet link may be null until worker completes

### COMMS-07: Move virtual appointment to in-person

- **Priority**: P1
- **Expected result**: Calendar event updates and old Meet conference is removed

### COMMS-08: Worker retry safety

- **Priority**: P2
- **Expected result**: Retrying notification work does not create duplicate appointments or duplicate calendar events

## 16. Concurrency and data integrity

Run these tests with two requests sent at nearly the same time.

### RACE-01: Same customer, same time

- **Priority**: P0
- **Expected result**: One booking succeeds; one fails
- **Expected failed detail**: `Slot no longer available.`
- **Expected data**: Only one appointment exists

### RACE-02: Same room, equipment, or associate

- **Priority**: P0
- **Repeat for each resource**
- **Expected result**: One booking succeeds; one fails; no overlap exists

### RACE-03: Same customer across centers

- **Priority**: P0
- **Setup**: Use C3 with valid services, staff, rooms, and availability at both centers
- **Expected result**: One booking succeeds globally

### RACE-04: Independent resources

- **Priority**: P1
- **Setup**: Use different customers, associates, rooms, and equipment at the same time
- **Expected result**: Both bookings succeed

### RACE-05: Two reschedules target same slot

- **Priority**: P0
- **Expected result**: One succeeds; one fails; both original appointments remain valid

### RACE-06: Same idempotency key sent together

- **Priority**: P0
- **Expected result**: One appointment only; both callers receive that appointment
- **Defect rule**: File a defect for conflict response or duplicate creation

### RACE-07: Duplicate lifecycle request

- **Priority**: P1
- **Expected result**: Appointment reaches one valid final state
- **Expected side effect**: No duplicate audit entries
- **Defect rule**: File a defect if both stale requests report a new successful transition

## 17. Final regression checklist

Before signing off:

- [ ] Staff can find virtual and in-person slots
- [ ] Staff can book doctor, specialty, combined, and care-team appointments
- [ ] Customer, staff, room, and equipment overlaps are blocked
- [ ] Center isolation works
- [ ] Appointment list, search, filters, and detail work
- [ ] Valid lifecycle transitions work
- [ ] Invalid lifecycle transitions do not change data
- [ ] Cancelled, completed, and no-show appointments release slots
- [ ] Reschedule releases old resources and reserves new resources
- [ ] Exceptions open, count, resolve, and acknowledge correctly
- [ ] Operating hours and roster rules work
- [ ] Blocks, leave, downtime, and closures affect calendars and slots
- [ ] Care team changes affect booking and team blocks correctly
- [ ] Operations numbers match test data
- [ ] Notification failure does not undo appointment actions
- [ ] Idempotency and concurrency do not create duplicates
- [ ] No endpoint exposes another center's data
- [ ] No validation failure leaves partial data
