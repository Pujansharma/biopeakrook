# Composite Program Add-Ons — Frontend ePRD

## 1. Purpose

Build the frontend workflow for selecting assessment and therapy catalogue
services, assigning them as repeatable add-ons to an existing composite
program, and listing the resulting program-service occurrences.

This workflow separates three concepts:

1. Category-specific catalogue services are selected through the assessment or
   therapy service APIs.
2. `POST /programs/composites/add-ons/` creates `ProgramService` occurrences.
3. A profile-scoped, paginated endpoint lists assigned occurrences across one
   or more composite programs.

Consultation services are outside this workflow.

## 2. Endpoint Summary

| Method | Purpose | Endpoint |
|---|---|---|
| `GET` | Browse assessment catalogue services | `/services/assessment-services/` |
| `GET` | Browse therapy catalogue services | `/services/therapy-services/` |
| `POST` | Create composite-program add-ons | `/programs/composites/add-ons/` |
| `GET` | List profile composite-program services | `/profiles/:profile_id/programs/composite-program-services/` |
| `GET` | List services for one composite program | `/programs/composites/programs/:program_id/services/` |

Catalogue service IDs and `ProgramService` IDs are different:

- A catalogue service ID comes from an assessment or therapy catalogue API and
  is submitted through `add_services[].id`.
- A program-service ID identifies one assigned occurrence and is used for
  result, document, redemption, and cancellation operations.

The assessment and therapy catalogue APIs expose different API contracts but
both resolve records from the shared service catalogue. Endpoint URLs are not
submitted in the add-on payload.

## 3. Access and Center Context

All requests require:

```http
Authorization: Bearer <access_token>
```

Administrators and associates can use this workflow. Associates require an
active assignment to the selected center.

Profile-scoped requests and associate add-on requests require:

```http
X-Center-ID: <center_uuid>
```

The profile must be active and assigned to the selected center. Returned
program services are limited to composite programs owned by or redeemable at
that center.

Customers cannot use these endpoints.

## 4. Catalogue Selection

The add-ons modal has separate **Assessment** and **Therapy** catalogue tabs.
Do not use the generic `/services/` endpoint for this workflow.

### 4.1 Assessment catalogue

```http
GET /services/assessment-services/?active=1&search=<search>&page=<page>&limit=<limit>
Authorization: Bearer <access_token>
```

### 4.2 Therapy catalogue

```http
GET /services/therapy-services/?active=1&search=<search>&page=<page>&limit=<limit>
Authorization: Bearer <access_token>
```

Both endpoints return the standard paginated envelope:

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<catalogue_service_uuid>",
      "name": "<string>",
      "service_category": "<Assessment|Therapy>",
      "service_category_code": "<assessment|therapy>",
      "image": "<url|null>",
      "is_active": true
    }
  ]
}
```

Assessment responses also include assessment-specific product metadata.
Therapy responses include therapy catalogue metadata. The frontend may consume
those additional documented fields but must use `id` as the add-on reference.

Do not exclude a catalogue service because it already exists in the selected
composite program. The same service may be assigned repeatedly.

## 5. Add-On Selection State

Each selection is an occurrence rather than a unique-service membership.

- Selecting a service creates one client-side line item.
- **Add another instance** creates another line with the same catalogue ID.
- Every line uses a temporary client-only key so repeated catalogue IDs remain
  independently editable and removable.
- Assessment lines do not show or submit a quantity.
- Every therapy line starts with a blank, required positive-integer session
  quantity.
- Repeated therapy lines may have different quantities.
- Do not show consultation services, prerequisite controls, catalogue pricing,
  or a calculated program price.

## 6. Create Add-Ons

### 6.1 Request

```http
POST /programs/composites/add-ons/
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
Content-Type: application/json
```

`X-Center-ID` is required for associates and optional for administrators.

```json
{
  "composite_program_id": "<composite_program_uuid>",
  "add_services": [
    {
      "id": "<assessment_service_uuid>"
    },
    {
      "id": "<assessment_service_uuid>"
    },
    {
      "id": "<therapy_service_uuid>",
      "quantity": 4
    },
    {
      "id": "<therapy_service_uuid>",
      "quantity": 2
    }
  ]
}
```

Assessment IDs must come from `/services/assessment-services/`. Therapy IDs
must come from `/services/therapy-services/`.

The backend resolves each service's stored `service_category`:

- assessment creates an `AssessmentProgramService` extension;
- therapy creates a `TherapyProgramService` extension whose `sessions_count`
  receives `quantity`.

Every new `ProgramService` uses `assignment_type=add_on`. Repeated service IDs
are intentional and must not be deduplicated.

The request is atomic. An invalid, inactive, unsupported, or quantity-invalid
entry prevents every occurrence in the request from being created.

### 6.2 Success response

```text
201 Created
```

The response remains the existing refreshed composite-program representation:

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<composite_program_uuid>",
    "uid": "<program_uid|null>",
    "name": "<string|null>",
    "services": "<three_item_program_service_preview|null>",
    "services_count": "<integer>",
    "add_ons_count": "<integer>",
    "assessment_services_count": "<integer>",
    "therapy_services_count": "<integer>",
    "consultation_services_count": "<integer>",
    "price": "<existing_program_price|null>",
    "is_active": "<boolean>",
    "updated_at": "<ISO-8601_datetime>",
    "...": "<remaining_existing_composite_program_fields>"
  }
}
```

`services` is a preview containing at most three occurrences. It is never the
authoritative complete list. The frontend must not append the preview to a
paginated list.

The complete composite-program response contract is defined in
[Composite Program Detail, Services, and Cancellation — Frontend ePRD](composite-program-detail-services-frontend-eprd.md).

All counters count assigned occurrences rather than distinct catalogue IDs.
`add_ons_count` overlaps with category counters and must not be added to them.
The returned program price remains unchanged by add-on creation.

## 7. Profile-Scoped Composite Program Services

This is the authoritative paginated list for the add-ons workflow:

```http
GET /profiles/:profile_id/programs/composite-program-services/
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
```

### 7.1 Query parameters

| Parameter | Required | Supported values | Behavior |
|---|---|---|---|
| `service_category` | No | `assessment`, `therapy` | Filters the catalogue-service category |
| `assignment_type` | No | `add_on`, `standalone` | Filters how the occurrence entered the program |
| `composite_program` | No | Composite program UUID | Restricts results to one program |
| `search` | No | String | Case-insensitive service-name search |
| `active` | No | `0`, `1` | Filters inactive or active occurrences |
| `page` | No | Positive integer | Requested page |
| `limit` | No | Positive integer up to the global maximum | Page size |

Do not send a `type` query parameter. `service_category` and `assignment_type`
match the corresponding backend model concepts.

Omitting `service_category` returns assessment and therapy occurrences.
Consultation occurrences are never returned by this endpoint.

Example:

```http
GET /profiles/:profile_id/programs/composite-program-services/?service_category=assessment&assignment_type=add_on&composite_program=<uuid>&search=blood&page=1&limit=10
```

Invalid enum or UUID filter values return a validation error.

### 7.2 Response

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<program_service_uuid>",
      "composite_program": {
        "id": "<composite_program_uuid>",
        "uid": "<program_uid|null>",
        "name": "<string|null>",
        "template": {
          "id": "<composite_template_uuid>",
          "code": "<template_sku>",
          "name": "<string>",
          "is_active": "<boolean>"
        }
      },
      "service": {
        "id": "<catalogue_service_uuid>",
        "name": "<string>",
        "service_category": "<Assessment|Therapy>",
        "service_category_code": "<assessment|therapy>",
        "image": "<url|null>"
      },
      "assignment_type": "<Add On|Standalone>",
      "assignment_type_code": "<add_on|standalone>",
      "sessions_count": "<integer|null>",
      "sessions_used": "<integer|null>",
      "sessions_cancelled": "<integer|null>",
      "redeem_code": "<string|null>",
      "results_count": "<integer>",
      "documents_count": "<integer>",
      "reports_count": "<integer>",
      "raw_data_count": "<integer>",
      "can_redeem": "<boolean>",
      "cancellation_reason": "<string|null>",
      "cancelled_by": "<user_object|null>",
      "cancelled_at": "<ISO-8601_datetime|null>",
      "cancelled_date": "<YYYY-MM-DD|null>",
      "created_date": "<YYYY-MM-DD>",
      "created_by": "<user_object|null>",
      "is_active": "<boolean>",
      "created_at": "<ISO-8601_datetime>",
      "updated_at": "<ISO-8601_datetime>"
    }
  ]
}
```

Therapy session and redeem-code fields are `null` for assessment occurrences.
Use the top-level program-service `id`, not `service.id`, as the frontend row
key and as the identifier for occurrence-specific operations.

For therapy occurrences, `sessions_count: 0` means unlimited sessions. Add-on
creation still requires a positive `quantity`; the unlimited value can appear
on existing standalone occurrences.

Results are ordered newest first.

## 8. Existing Program-Specific List

The existing endpoint remains available and keeps its current response:

```http
GET /programs/composites/programs/:program_id/services/
```

It continues to support its existing `category` filter and additionally
supports:

```text
assignment_type=add_on
assignment_type=standalone
```

The profile-scoped endpoint is preferred for the add-ons screen because it
supports validated service-category, assignment-type, program, name, and active
filters in one paginated contract.

## 9. Frontend State and Refresh Behavior

Keep catalogue queries, assigned-service list queries, selected occurrence
lines, and submission state separate.

On successful creation:

1. Close the modal.
2. Replace cached composite-program metadata with the POST response.
3. Invalidate every profile-scoped composite-program-service query for the
   profile.
4. Invalidate the existing program-specific list if that screen is cached.
5. Refetch the currently visible assigned-service page.

Do not optimistically create rows, increment counters, or treat the POST preview
as paginated data.

On failure, keep the modal open, preserve every repeated line and entered
therapy quantity, and show nested or general `add_services` errors without
partially updating local state.

## 10. Frontend Types

```ts
type ServiceCategoryCode = "assessment" | "therapy";
type AssignmentTypeCode = "add_on" | "standalone";

interface AddOnRequestItem {
  id: string;
  quantity?: number;
}

interface CompositeAddOnRequest {
  composite_program_id: string;
  add_services: AddOnRequestItem[];
}

interface CompositeProgramReference {
  id: string;
  uid: string | null;
  name: string | null;
  template: {
    id: string;
    code: string;
    name: string;
    is_active: boolean;
  };
}

interface CompositeProgramServiceListItem {
  id: string;
  composite_program: CompositeProgramReference;
  service: {
    id: string;
    name: string;
    service_category: "Assessment" | "Therapy";
    service_category_code: ServiceCategoryCode;
    image: string | null;
  };
  assignment_type: "Add On" | "Standalone";
  assignment_type_code: AssignmentTypeCode;
  sessions_count: number | null;
  sessions_used: number | null;
  sessions_cancelled: number | null;
  redeem_code: string | null;
  results_count: number;
  documents_count: number;
  reports_count: number;
  raw_data_count: number;
  can_redeem: boolean;
  is_active: boolean;
}
```

## 11. Acceptance Criteria

- Assessment selection uses `/services/assessment-services/`.
- Therapy selection uses `/services/therapy-services/`.
- The generic `/services/` endpoint is not used by this workflow.
- Associates can read both category catalogues.
- The POST body retains `add_services` and sends catalogue UUIDs, not URLs.
- Repeated service IDs create distinct program-service occurrences.
- Every therapy occurrence maps `quantity` to its own session allocation.
- Consultation services cannot be selected, created, or returned by the new
  profile-scoped endpoint.
- POST returns refreshed composite-program metadata and counters, not an
  unpaginated complete service list.
- The profile list supports `service_category`, `assignment_type`,
  `composite_program`, `search`, and `active` independently and together.
- No frontend request uses a `type` query parameter.
- Every result identifies its owning composite program.
- Repeated catalogue services render as separate rows keyed by ProgramService
  UUID.
- The existing program-specific service list remains compatible and supports
  `assignment_type`.
- Program pricing and template prerequisites remain outside add-on behavior.
