# Composite Program Detail, Services, and Cancellation — Frontend ePRD

## 1. Purpose

Build the frontend detail experience for one assigned composite program and its
complete service list.

This ePRD covers only these backend routes:

| Method | Purpose | Endpoint |
|---|---|---|
| `GET` | Retrieve composite-program details and a service preview | `/programs/composites/programs/:program_id/` |
| `PATCH` | Partially update editable program fields | `/programs/composites/programs/:program_id/` |
| `PUT` | Update editable program fields | `/programs/composites/programs/:program_id/` |
| `GET` | Retrieve the complete paginated service list | `/programs/composites/programs/:program_id/services/` |
| `POST` | Cancel the composite program | `/programs/composites/programs/:program_id/cancel/` |

Adding repeatable assessment and therapy occurrences is specified separately
in [Composite Program Add-Ons — Frontend ePRD](composite-program-add-ons-frontend-eprd.md).

`program_id` is the composite program UUID. It is also the UUID of the linked
base program because the composite program uses the program relation as its
primary key.

## 2. Access and Request Context

All requests require a valid JWT:

```http
Authorization: Bearer <access_token>
```

Associate requests also require:

```http
X-Center-ID: <center_uuid>
```

An associate must have an active assignment to that center. Detail GET and
service-list GET access do not require the `packages` feature. PUT, PATCH, and
cancellation retain the `packages` feature or all-features requirement. The
requested program must be owned by or redeemable at the selected center.

Administrators can access the detail, update, and service-list operations
without `X-Center-ID`. However, `can_redeem` is center-contextual. The frontend
should send the currently selected center for administrators when it needs a
center-specific `can_redeem` value. Without a center header, only global
services are returned with `can_redeem: true` for an administrator.

The cancel operation requires `X-Center-ID` for both administrators and
associates. The program must be owned by or redeemable at the selected center.

Customers cannot use these endpoints.

Mutation requests also require:

```http
Content-Type: application/json
```

## 3. Product Behavior

The composite-program detail page must provide:

- program identity and client summary;
- owning and redeemable center information;
- template reference information;
- lifecycle, pricing, cancellation, and audit metadata;
- server-maintained service counters;
- a complete, filterable, paginated service list;
- editing for notes and expiry date only;
- an explicit, confirmed cancellation action.

The frontend must not reconstruct server-maintained counts or redemption
eligibility.

### 3.1 Service preview versus complete list

The detail endpoint's `services` field is a preview containing at most three
services. It is `null`, not an empty array, when no preview service is present.

The services endpoint is the authoritative source for the complete service
list. `services_count` is the authoritative total count and may be greater than
the detail response's preview length.

### 3.2 Counter semantics

- `services_count` counts all assigned program services.
- `assessment_services_count`, `therapy_services_count`, and
  `consultation_services_count` count all assigned services in their respective
  categories.
- `add_ons_count` counts services whose assignment type is `add_on`.
- An add-on also belongs to one service category. Therefore, `add_ons_count`
  overlaps with the category counters and must not be added to them.
- Counts include inactive and cancelled assigned services.

## 4. GET Composite Program Detail

### 4.1 Request

```http
GET /programs/composites/programs/:program_id/
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
```

The `X-Center-ID` header is required for associates and recommended for an
administrator working in a selected center context.

Request body:

```json
null
```

### 4.2 Success status

```text
200 OK
```

### 4.3 Response structure

```json
{
  "detail": "Details.",
  "data": {
    "id": "<composite_program_uuid>",
    "uid": "<program_uid|null>",
    "name": "<string|null>",
    "assessment_type": "<Baseline|null>",
    "assessment_type_code": "<baseline|null>",
    "profile": {
      "id": "<customer_profile_uuid>",
      "contact_email": "<email|null>",
      "phone": "<phone|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "gender": "<display_string|null>",
      "date_of_birth": "<YYYY-MM-DD|null>",
      "image": "<url|null>",
      "home_center": {
        "id": "<center_uuid>",
        "code": "<string>",
        "name": "<string>"
      },
      "created_at": "<ISO-8601_datetime>",
      "updated_at": "<ISO-8601_datetime>"
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
      "is_active": "<boolean>"
    },
    "program_type": "composite",
    "notes": "<string|null>",
    "expires_at": "<YYYY-MM-DD|null>",
    "is_complimentary": "<boolean>",
    "price": "<decimal_string|null>",
    "redeemable_centers": [
      {
        "id": "<center_uuid>",
        "code": "<string>",
        "name": "<string>"
      }
    ],
    "redeemable_centers_count": "<integer>",
    "services": [
      {
        "id": "<program_service_uuid>",
        "service": {
          "id": "<service_uuid>",
          "name": "<string>",
          "service_category": "<Therapy|Assessment|Consultation>",
          "service_category_code": "<therapy|assessment|consultation>",
          "image": "<url|null>"
        },
        "service_assignment_type": "<Standalone|Add On>",
        "service_assignment_type_code": "<standalone|add_on>",
        "sessions_count": "<integer|null>",
        "sessions_used": "<integer|null>",
        "sessions_cancelled": "<integer|null>",
        "redeem_code": "<string|null>",
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
    ],
    "services_count": "<integer>",
    "add_ons_count": "<integer>",
    "assessment_services_count": "<integer>",
    "therapy_services_count": "<integer>",
    "consultation_services_count": "<integer>",
    "cancellation_reason": "<string|null>",
    "cancelled_by": "<user_object|null>",
    "cancelled_at": "<ISO-8601_datetime|null>",
    "cancelled_date": "<YYYY-MM-DD|null>",
    "created_date": "<YYYY-MM-DD>",
    "is_active": "<boolean>",
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>",
    "created_by": "<user_object|null>"
  }
}
```

Nullable nested values have these additional rules:

- `profile.home_center` can be `null` when no primary center assignment is
  available.
- `services` can be `null`; otherwise it contains no more than three items.
- `sessions_count`, `sessions_used`, `sessions_cancelled`, and `redeem_code`
  are populated only for therapy services. They are `null` for assessment and
  consultation services.
- A therapy `sessions_count` value of `0` means unlimited sessions; it does not
  mean that the service is unavailable.

User objects use this structure:

```json
{
  "id": "<user_uuid>",
  "email": "<email|null>",
  "first_name": "<string>",
  "last_name": "<string>",
  "image": "<url|null>",
  "last_login": "<ISO-8601_datetime|null>"
}
```

### 4.4 Fields not returned

The current endpoint does not return top-level `description` or
`template_description`. Template description is available only at
`composite_template.description`.

The frontend must not depend on fields present in older documentation but
absent from the response structure above.

## 5. PATCH or PUT Composite Program Detail

### 5.1 Frontend method

Use `PATCH` for ordinary edits. Although `PUT` is supported, the backend treats
the editable fields as optional and does not require a complete replacement
payload.

### 5.2 Editable fields

Only these fields are editable through this endpoint:

| Field | Type | Rules |
|---|---|---|
| `notes` | `string \| null` | Optional; blank string is accepted |
| `expires_at` | `YYYY-MM-DD \| null` | Optional; a non-null value cannot be earlier than the backend's current local date |

PATCH request example:

```http
PATCH /programs/composites/programs/:program_id/
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
Content-Type: application/json
```

```json
{
  "notes": "Client requested morning sessions.",
  "expires_at": "2026-12-31"
}
```

To remove both optional values:

```json
{
  "notes": null,
  "expires_at": null
}
```

### 5.3 Immutable fields

The frontend must never submit the full GET response as an update payload.

The backend explicitly rejects these submitted fields:

- `name`;
- `assessment_type`;
- `assessment_type_code`;
- `profile_id`;
- `composite_template_id`;
- `redeemable_centers`;
- `is_complimentary`;
- `price`;
- `created_date`.

All nested objects, identifiers, services, counts, cancellation data, status,
UID, creator data, and timestamps must remain read-only in this screen.

### 5.4 PATCH success response

```text
200 OK
```

```json
{
  "detail": "Updated successfully.",
  "data": "<complete_composite_program_detail_object>"
}
```

`data` uses the complete response structure from section 4.3.

### 5.5 PUT success response

```text
200 OK
```

```json
{
  "detail": "Modified successfully.",
  "data": "<complete_composite_program_detail_object>"
}
```

After either success, replace the local detail object with `response.data`.
Do not merge computed counters or nested objects manually.

## 6. GET Composite Program Services

### 6.1 Request

```http
GET /programs/composites/programs/:program_id/services/?page=1&limit=10&category=therapy&assignment_type=add_on
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
```

Request body:

```json
null
```

### 6.2 Query parameters

| Parameter | Required | Values | Behavior |
|---|---|---|---|
| `page` | No | Positive integer | Requested page; defaults to the first page |
| `limit` | No | Integer up to `50` | Page size; defaults to `10` and is capped at `50` |
| `category` | No | `therapy`, `assessment`, `consultation` | Exact service-category filter |
| `assignment_type` | No | `add_on`, `standalone` | Exact ProgramService assignment-type filter |

The backend currently does not validate `category` against the documented
enum. Any other value normally produces an empty result. The frontend must send
only the three supported codes.

Services are returned newest first.

### 6.3 Success status

```text
200 OK
```

### 6.4 Response structure

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    {
      "id": "<program_service_uuid>",
      "service": {
        "id": "<service_uuid>",
        "name": "<string>",
        "service_category": "<Therapy|Assessment|Consultation>",
        "service_category_code": "<therapy|assessment|consultation>",
        "image": "<url|null>"
      },
      "service_assignment_type": "<Standalone|Add On>",
      "service_assignment_type_code": "<standalone|add_on>",
      "sessions_count": "<integer|null>",
      "sessions_used": "<integer|null>",
      "sessions_cancelled": "<integer|null>",
      "redeem_code": "<string|null>",
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

An empty page uses:

```json
{
  "detail": "All data.",
  "count": 0,
  "next": null,
  "previous": null,
  "data": []
}
```

The list endpoint does not perform a separate parent lookup. A nonexistent or
inaccessible `program_id` therefore returns a successful empty paginated list
instead of a program-specific `404`.

## 7. POST Cancel Composite Program

### 7.1 Request

```http
POST /programs/composites/programs/:program_id/cancel/
Authorization: Bearer <access_token>
X-Center-ID: <center_uuid>
Content-Type: application/json
```

`X-Center-ID` is required for every cancel request, including administrator
requests. The selected center must exist, and the composite program must be
owned by or redeemable at that center.

Request payload:

```json
{
  "cancellation_reason": "<string|null>",
  "cancelled_date": "<YYYY-MM-DD>"
}
```

### 7.2 Request field rules

| Field | Required | Rules |
|---|---|---|
| `cancellation_reason` | No | Accepts a string, blank string, or `null` |
| `cancelled_date` | No | Must be a valid date when supplied; defaults to the backend's current local date when omitted; `null` is not accepted |

The backend does not currently restrict `cancelled_date` to today or a past
date. The frontend should use the business-approved date-selection policy and
must not assume the API performs that policy validation.

Minimal valid request:

```json
{}
```

Request with a reason while using the default cancellation date:

```json
{
  "cancellation_reason": "Cancelled at the client's request."
}
```

### 7.3 Success status and response

```text
201 Created
```

```json
{
  "detail": "Create success.",
  "data": {
    "cancellation_reason": "<string|null>",
    "cancelled_date": "<YYYY-MM-DD>",
    "cancelled_by": {
      "id": "<user_uuid>",
      "email": "<email|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<ISO-8601_datetime|null>"
    },
    "cancelled_at": "<ISO-8601_datetime|null>"
  }
}
```

The response is not a complete composite-program object. After success, the
frontend must refetch both:

- `/programs/composites/programs/:program_id/`;
- `/programs/composites/programs/:program_id/services/` using the current
  pagination and category state.

The detail refetch will expose `is_active: false` and the saved cancellation
metadata.

### 7.4 Current backend cancellation effects

The current implementation performs these actions atomically:

- marks the composite program inactive;
- marks the linked base program inactive;
- saves the reason, cancelling user, and cancellation date;
- cancels active therapy program-service records, records their remaining
  sessions as cancelled, and creates cancellation redemption history when
  remaining sessions are greater than zero.

Assessment and consultation program-service records are not deactivated by the
current cancellation helper. Therefore, the frontend must not optimistically
mark every locally cached service inactive. It must use the service-list
refetch as the source of truth.

`cancelled_at` is populated by the current helper when it processes at least
one active therapy service. It can remain `null` when the composite has no
active therapy service, which is why the response type is nullable.

### 7.5 Cancel-specific errors

Missing center header:

```json
{
  "detail": "X-Center-ID header is required."
}
```

Unknown center:

```json
{
  "detail": "Center not found with this ID."
}
```

Program not found in the selected center context:

```json
{
  "detail": "Composite program not found with this ID."
}
```

Already cancelled:

```json
{
  "detail": "Composite program is already cancelled."
}
```

Expected statuses are `400` for a missing header, invalid request data, or an
already-cancelled program, and `404` for an unknown center or a program that is
not available in the selected center context.

## 8. `can_redeem` Rules

`can_redeem` is supplied by the API and must not be calculated by the
frontend.

It is `true` when either:

- the service is global; or
- the service has an active assignment to the center represented by the
  request context.

For associates, the request context is the required `X-Center-ID`. For
administrators, it is the optional `X-Center-ID`. Changing the selected center
must trigger a refetch of both detail and service-list data so every
`can_redeem` value is recalculated by the backend.

## 9. Error Response Structure

Errors do not include `success` or `data`.

Field validation error:

```json
{
  "detail": {
    "expires_at": [
      "Expiry date cannot be earlier than today's date."
    ]
  }
}
```

Immutable-field error:

```json
{
  "detail": "These fields cannot be updated: name, price."
}
```

General authentication, permission, or not-found error:

```json
{
  "detail": "<error_message>"
}
```

Expected status handling:

| Status | Frontend behavior |
|---|---|
| `400` | Map object-shaped `detail` to form fields; otherwise show a notification |
| `401` | Start the application's authentication recovery flow |
| `403` | Show an access-denied state |
| `404` | Show program-not-found for the detail request |
| `500` | Show the standard retryable server-error state |

The frontend must support both string-shaped and object-shaped `detail`.

## 10. Recommended Frontend Data Contracts

```ts
type ServiceCategoryCode = "therapy" | "assessment" | "consultation";
type ServiceAssignmentTypeCode = "standalone" | "add_on";

interface MinimumCenter {
  id: string;
  code: string;
  name: string;
}

interface BaseUser {
  id: string;
  email: string | null;
  first_name: string;
  last_name: string;
  image: string | null;
  last_login: string | null;
}

interface ProgramService {
  id: string;
  service: {
    id: string;
    name: string;
    service_category: "Therapy" | "Assessment" | "Consultation";
    service_category_code: ServiceCategoryCode;
    image: string | null;
  };
  service_assignment_type: "Standalone" | "Add On";
  service_assignment_type_code: ServiceAssignmentTypeCode;
  sessions_count: number | null;
  sessions_used: number | null;
  sessions_cancelled: number | null;
  redeem_code: string | null;
  can_redeem: boolean;
  cancellation_reason: string | null;
  cancelled_by: BaseUser | null;
  cancelled_at: string | null;
  cancelled_date: string | null;
  created_date: string;
  created_by: BaseUser | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface CompositeProgramDetail {
  id: string;
  uid: string | null;
  name: string | null;
  assessment_type: "Baseline" | null;
  assessment_type_code: "baseline" | null;
  profile: {
    id: string;
    contact_email: string | null;
    phone: string | null;
    first_name: string;
    last_name: string;
    gender: string | null;
    date_of_birth: string | null;
    image: string | null;
    home_center: MinimumCenter | null;
    created_at: string;
    updated_at: string;
  };
  center: MinimumCenter;
  composite_template: {
    id: string;
    name: string;
    description: string | null;
    is_active: boolean;
  };
  program_type: "composite";
  notes: string | null;
  expires_at: string | null;
  is_complimentary: boolean;
  price: string | null;
  redeemable_centers: MinimumCenter[];
  redeemable_centers_count: number;
  services: ProgramService[] | null;
  services_count: number;
  add_ons_count: number;
  assessment_services_count: number;
  therapy_services_count: number;
  consultation_services_count: number;
  cancellation_reason: string | null;
  cancelled_by: BaseUser | null;
  cancelled_at: string | null;
  cancelled_date: string | null;
  created_date: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: BaseUser | null;
}

interface DetailResponse {
  detail: "Details.";
  data: CompositeProgramDetail;
}

interface UpdateResponse {
  detail: "Updated successfully." | "Modified successfully.";
  data: CompositeProgramDetail;
}

interface ServicesResponse {
  detail: "All data.";
  count: number;
  next: string | null;
  previous: string | null;
  data: ProgramService[];
}

interface CompositeProgramUpdatePayload {
  notes?: string | null;
  expires_at?: string | null;
}

interface CompositeProgramCancelPayload {
  cancellation_reason?: string | null;
  cancelled_date?: string;
}

interface CompositeProgramCancellation {
  cancellation_reason: string | null;
  cancelled_date: string;
  cancelled_by: BaseUser;
  cancelled_at: string | null;
}

interface CancelResponse {
  detail: "Create success.";
  data: CompositeProgramCancellation;
}
```

## 11. Frontend State Requirements

Maintain these state groups independently:

- detail data, loading, error, and update state;
- services data, count, pagination, category, assignment type, loading, and
  error state;
- selected center context;
- edit form dirty state;
- cancellation confirmation, submission, and error state.

Changing page, limit, category, assignment type, program ID, or center context
must invalidate and refetch the affected service query. Changing program ID or
center context must also refetch detail data.

Do not use preview services as page-one service-list data because the preview
has no pagination metadata and is limited independently.

After cancellation, invalidate and refetch both detail and service-list state.
Do not derive a complete updated program from the compact cancellation
response.

## 12. UI Requirements

### Detail summary

- Show `uid` as the human-facing program reference and `id` only where a UUID is
  operationally useful.
- Provide the **Add add-ons** action described in the standalone add-ons ePRD
  when the program is active and unexpired.
- Show the client, owning center, template, expiry, active state, pricing mode,
  and creation metadata.
- Show cancellation metadata when it is present.
- Render all counters directly from the detail response.
- Do not calculate a total by summing category and add-on counters.

### Service list

- Provide All, Therapy, Assessment, and Consultation filters.
- Send category codes, never display labels, to the API.
- Provide All, Add On, and Standalone assignment filters and send only
  `assignment_type_code` values.
- Show service name, category, assignment type, session usage, status, and
  redemption eligibility.
- Distinguish `sessions_count: 0` as Unlimited for therapy services.
- Hide or mark session and redeem-code fields as not applicable for
  non-therapy services.
- Use the API's pagination URLs or preserve `page` and `limit` in route/query
  state.

### Edit form

- Expose only notes and expiry date.
- Build the PATCH body from changed editable fields only.
- Allow clearing either field with `null`.
- Apply the backend validation error to the expiry field when `detail` is an
  object containing `expires_at`.
- Replace local detail data with the successful response.

### Cancel action

- Show the action only when `is_active` is `true` and the current user has
  access to it.
- Require explicit user confirmation because cancellation changes program and
  service state.
- Allow an optional reason and cancellation date.
- Default the displayed cancellation date to the user's current local date,
  while allowing the backend default by omitting the field.
- Always send the selected `X-Center-ID`, including for administrators.
- Disable repeated submission while the request is pending.
- After success, refetch detail and services before presenting the final state.
- If the API reports that the program is already cancelled, refetch the detail
  instead of offering another cancellation attempt.

## 13. Acceptance Criteria

- The detail request uses
  `/programs/composites/programs/:program_id/` and renders the documented
  response without depending on undocumented fields.
- The UI shows `uid` and does not expect top-level `description` or
  `template_description`.
- An associate request always includes the selected `X-Center-ID`.
- A center-context change refetches API-calculated `can_redeem` values.
- The detail service preview is never treated as the complete service list.
- The services screen supports `page`, `limit`, and the three documented
  category codes.
- The services screen supports `assignment_type=add_on|standalone` without
  changing the existing response structure.
- Empty service results render a valid empty state.
- The frontend displays all server-maintained counters without recalculating
  them.
- `add_ons_count` is never added to category counts.
- Only `notes` and `expires_at` are submitted by the edit form.
- A past non-null expiry date displays the backend field error.
- String-shaped and object-shaped error details are both handled.
- Cancellation uses
  `/programs/composites/programs/:program_id/cancel/` with `POST`.
- Every cancellation request includes `X-Center-ID`.
- The cancellation form submits only `cancellation_reason` and/or
  `cancelled_date`.
- A successful `201` response triggers detail and service-list refetches.
- The UI does not optimistically mark all cached services inactive.
- An already-cancelled response removes or disables the cancellation action
  after refreshing detail state.
- No frontend workflow attempts to delete a composite program through these
  endpoints.
