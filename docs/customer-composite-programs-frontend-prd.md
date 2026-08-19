# Customer Composite Programs — Frontend PRD

## 1. Summary

Build the customer-profile composite-program experience for administrators and
authorized associates. The frontend can list programs for a customer profile,
assign a composite template as a new program, and edit a limited set of
program-level fields.

This feature uses only three API operations:

| Method | Purpose | Endpoint |
|---|---|---|
| `GET` | List a customer's composite programs | `/profiles/:profile_id/programs/composite-programs/` |
| `POST` | Assign a composite template to the customer | `/profiles/:profile_id/programs/composite-programs/` |
| `PATCH` | Edit allowed program fields | `/programs/composites/programs/:composite_program_id/` |

Services are assigned from the selected composite template during creation.
They are always read-only in this feature and cannot be added, removed, or
modified through PATCH.

Post-creation assessment and therapy add-ons and the profile-scoped assigned
service list are documented separately in
[Composite Program Add-Ons — Frontend ePRD](composite-program-add-ons-frontend-eprd.md).

## 2. Access and Headers

All requests require:

```http
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
Content-Type: application/json
```

- Administrators can access a customer profile assigned to the selected center.
- Associates must be actively assigned to the selected center and actively
  linked to the customer profile at that center.
- Customers cannot use these endpoints.
- The `X-Center-ID` value becomes the owning center for a program created by POST.

## 3. Data Semantics

Top-level `description` is the editable program description stored on
`composite_program.program.description`. The nested `composite_template`
reference exposes only `id`, `code`, `name`, and `is_active`.

The `services` field is a preview of assigned services. `services_count` is the
authoritative total. The service-category counters include both template
services and add-ons. `add_ons_count` is an overlapping subset and must not be
added to the category counters or to `services_count`. All counters include
inactive and cancelled assigned services. The frontend must treat every count,
service, and service-session field as read-only.

## 4. GET — List Customer Composite Programs

### Endpoint

```http
GET /profiles/:profile_id/programs/composite-programs/
```

### Query parameters

| Parameter | Values | Behavior |
|---|---|---|
| `active` | `0`, `1` | Filters inactive or active programs |
| `expired` | `0`, `1` | Filters expired or unexpired programs |
| `search` | string | Case-insensitive template code/name or program UID search |
| `page` | positive integer | Requested results page |
| `limit` | `1`–`50` | Page size |

The endpoint returns all composite programs belonging to the authorized
customer profile. Service `can_redeem` values are evaluated against the center
in `X-Center-ID`.

### Request payload

```json
null
```

### Success response

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "<composite_program_uuid>",
      "profile": {
        "id": "<customer_profile_uuid>",
        "contact_email": "<email|null>",
        "phone": "<phone>",
        "first_name": "<string>",
        "last_name": "<string>",
        "gender": "<string|null>",
        "date_of_birth": "<date|null>",
        "image": "<url|null>",
        "home_center": {
          "id": "<center_uuid>",
          "code": "<string>",
          "name": "<string>"
        },
        "created_at": "<datetime>",
        "updated_at": "<datetime>"
      },
      "center": {
        "id": "<center_uuid>",
        "code": "<string>",
        "name": "<string>"
      },
      "composite_template": {
        "id": "<composite_template_uuid>",
        "code": "<template_sku>",
        "name": "<string>",
        "is_active": true
      },
      "name": "<string|null>",
      "assessment_type": "<Baseline|null>",
      "assessment_type_code": "<baseline|null>",
      "program_type": "composite",
      "notes": "<string|null>",
      "description": "<program_description|null>",
      "expires_at": "<date|null>",
      "is_complimentary": true,
      "price": "<decimal_string|null>",
      "redeemable_centers": [
        {
          "id": "<center_uuid>",
          "code": "<string>",
          "name": "<string>"
        }
      ],
      "redeemable_centers_count": 1,
      "services": [
        {
          "id": "<program_service_uuid>",
          "service": {
            "id": "<service_uuid>",
            "name": "<string>",
            "service_category": "<string>",
            "service_category_code": "<therapy|assessment|consultation>",
            "image": "<url|null>"
          },
          "service_assignment_type": "<string>",
          "service_assignment_type_code": "<standalone|add_on>",
          "sessions_count": "<integer|null>",
          "sessions_used": "<integer|null>",
          "sessions_cancelled": "<integer|null>",
          "redeem_code": "<string|null>",
          "can_redeem": true,
          "cancellation_reason": "<string|null>",
          "cancelled_by": "<user_object|null>",
          "cancelled_at": "<datetime|null>",
          "cancelled_date": "<date|null>",
          "created_date": "<date>",
          "created_by": "<user_object|null>",
          "is_active": true,
          "created_at": "<datetime>",
          "updated_at": "<datetime>"
        }
      ],
      "services_count": 1,
      "add_ons_count": 0,
      "assessment_services_count": 1,
      "therapy_services_count": 0,
      "consultation_services_count": 0,
      "cancellation_reason": "<string|null>",
      "cancelled_by": "<user_object|null>",
      "cancelled_at": "<datetime|null>",
      "cancelled_date": "<date|null>",
      "created_date": "<date>",
      "is_active": true,
      "created_at": "<datetime>",
      "updated_at": "<datetime>",
      "created_by": "<user_object|null>"
    }
  ]
}
```

## 5. POST — Create Customer Composite Program

### Endpoint

```http
POST /profiles/:profile_id/programs/composite-programs/
```

The customer profile is derived from `:profile_id`. Do not include a profile ID
or center ID in the request body. The owning center is derived from
`X-Center-ID`.

### Request payload structure

For a template containing at least one active assessment service:

```json
{
  "composite_template_id": "<composite_template_uuid>",
  "name": "<composite_program_name|null>",
  "assessment_type": "baseline",
  "notes": "<string|null>",
  "expires_at": "<date>",
  "is_complimentary": true,
  "price": null,
  "redeemable_centers": [
    {
      "id": "<center_uuid>"
    }
  ],
  "created_date": "<date>"
}
```

For a template without an active assessment service, omit the assessment-only
fields:

```json
{
  "composite_template_id": "<composite_template_uuid>",
  "notes": "<string|null>",
  "expires_at": "<date>",
  "is_complimentary": true,
  "price": null,
  "redeemable_centers": [
    {
      "id": "<center_uuid>"
    }
  ],
  "created_date": "<date>"
}
```

### Field rules

| Field | Required | Rules |
|---|---|---|
| `composite_template_id` | Yes | Must identify an active template with active services |
| `name` | No | Currently used only for assessment-service programs; accepts a string, `""`, or `null`; `""` is stored as `null` |
| `assessment_type` | Conditional | Accepts `baseline` or `null`; required when the template contains at least one active assessment service |
| `notes` | No | Nullable and may be blank |
| `expires_at` | Yes | Cannot be earlier than the current local date |
| `is_complimentary` | No | Defaults to `true` |
| `price` | Conditional | Required when `is_complimentary` is `false` |
| `redeemable_centers` | Yes | Non-empty; every center must be actively assigned to the profile |
| `created_date` | No | Defaults on the backend when omitted |

The frontend must not send services. The backend derives all active services and
their category-specific assignments from the selected template.

`description` is not a POST field. It is available only through the limited
composite-program PATCH contract.

### Success response

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<composite_program_uuid>",
    "profile": "<profile_object>",
    "center": "<center_object>",
    "composite_template": "<composite_template_object>",
    "name": "<string|null>",
    "assessment_type": "<Baseline|null>",
    "assessment_type_code": "<baseline|null>",
    "program_type": "composite",
    "notes": "<string|null>",
    "description": "<program_description|null>",
    "expires_at": "<date|null>",
    "is_complimentary": true,
    "price": "<decimal_string|null>",
    "redeemable_centers": ["<center_object>"],
    "redeemable_centers_count": 1,
    "services": ["<program_service_object>"],
    "services_count": 1,
    "add_ons_count": 0,
    "assessment_services_count": 1,
    "therapy_services_count": 0,
    "consultation_services_count": 0,
    "cancellation_reason": null,
    "cancelled_by": null,
    "cancelled_at": null,
    "cancelled_date": null,
    "created_date": "<date>",
    "is_active": true,
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": "<user_object>"
  }
}
```

Nested objects use the same structures documented in the GET response.

## 6. PATCH — Update Composite Program

### Endpoint

```http
PATCH /programs/composites/programs/:composite_program_id/
```

### Allowed request fields

PATCH is partial. Send only changed values and at least one of these fields:

```json
{
  "notes": "<string|null>",
  "expires_at": "<date|null>",
  "description": "<program_description|null>"
}
```

Examples of valid partial payloads:

```json
{
  "notes": "Customer requested morning sessions."
}
```

```json
{
  "expires_at": "2026-12-31",
  "description": "Updated customer-specific program description."
}
```

### PATCH restrictions

Only the following program fields may change:

- `notes`
- `expires_at`
- `description`

The frontend must never submit any of these fields through PATCH:

- `services` or any service/session field
- `composite_template_id` or `composite_template`
- `name`, `assessment_type`, or `assessment_type_code`
- `profile`, `profile_id`, or customer identity fields
- `center` or owning-center fields
- `redeemable_centers`
- `is_complimentary` or `price`
- counts, cancellation fields, status, creator, or timestamps

Updating top-level `description` changes only
`composite_program.program.description`. It must not update
`composite_template.description`, `name`, `assessment_type`, or
`template_description`.

### Success response

```json
{
  "detail": "Updated successfully.",
  "data": {
    "id": "<composite_program_uuid>",
    "profile": "<profile_object>",
    "center": "<center_object>",
    "composite_template": "<composite_template_object>",
    "name": "<string|null>",
    "assessment_type": "<Baseline|null>",
    "assessment_type_code": "<baseline|null>",
    "program_type": "composite",
    "notes": "<updated_string|null>",
    "description": "<updated_program_description|null>",
    "expires_at": "<updated_date|null>",
    "is_complimentary": true,
    "price": "<decimal_string|null>",
    "redeemable_centers": ["<center_object>"],
    "redeemable_centers_count": 1,
    "services": ["<unchanged_program_service_object>"],
    "services_count": 1,
    "add_ons_count": 0,
    "assessment_services_count": 1,
    "therapy_services_count": 0,
    "consultation_services_count": 0,
    "cancellation_reason": "<string|null>",
    "cancelled_by": "<user_object|null>",
    "cancelled_at": "<datetime|null>",
    "cancelled_date": "<date|null>",
    "created_date": "<date>",
    "is_active": true,
    "created_at": "<datetime>",
    "updated_at": "<datetime>",
    "created_by": "<user_object|null>"
  }
}
```

## 7. Error Response

All errors use the project response envelope:

```json
{
  "detail": "<string|object>"
}
```

When `detail` is an object, the frontend must map its field keys to the relevant
inputs. When it is a string, display it as the fallback notification. Expected
failures include inaccessible profiles, invalid center context, inactive
templates, templates without active services, unavailable services, invalid
redeemable centers, a missing or invalid assessment type when the template
contains an active assessment service, past expiry dates, and a missing price
for a non-complimentary program.

## 8. Frontend Requirements

### List state

- Show the composite-program name, assessment type, program description,
  expiry, active/expired state,
  total service count, service-category counts, add-on count, and owning center.
- Provide active and expired filters and preserve pagination in the URL state.
- Treat `services` as a preview, `services_count` as the total, and
  `add_ons_count` as a subset that overlaps the category counts.
- Display a clear empty state when `data` is empty.

### Create state

- Load the profile context from the page route; do not ask the user to select the
  profile again.
- Submit the selected template identifier, program fields, and redeemable center
  identifiers.
- Show the optional name input only for templates containing an active
  assessment service. Require assessment type for those templates.
- Show template services as a read-only preview before submission.
- Require price only when the complimentary toggle is off.

### Edit state

- Render only notes, expiry date, and program description as editable fields.
- Show name, assessment type, template, centers, services, prices, and service
  sessions as read-only.
- Build PATCH payloads from changed editable fields only.
- Never submit the complete GET object back to PATCH.
- After success, replace the local program object with the PATCH response data.

## 9. Acceptance Criteria

- GET lists only the selected profile's composite programs and supports active,
  expired, and pagination parameters.
- POST never sends `profile_id`, `center_id`, or services.
- POST allows name to be omitted or null and conditionally requires assessment
  type for templates containing an active assessment service.
- POST renders field-level backend validation errors correctly.
- PATCH uses `/programs/composites/programs/:composite_program_id/`.
- PATCH submits only notes, expiry, and/or program description.
- Editing the program description does not alter template metadata.
- Services and service sessions cannot be edited from any screen in this flow.
- All four composite-specific counters are displayed from the API response and
  are never calculated or submitted by the frontend.
- Successful POST and PATCH responses update the UI without requiring the
  frontend to reconstruct nested program data.
