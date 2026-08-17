# Program Service Detail and Cancellation — Frontend ePRD

## 1. Purpose

Build the frontend detail and cancellation experience for assigned services
within a program.

This ePRD covers these backend routes:

| Method | Purpose | Endpoint |
|---|---|---|
| `GET` | Retrieve an assigned assessment service | `/programs/program-services/assessment-services/:program_service_id/` |
| `GET` | Retrieve an assigned therapy service | `/programs/program-services/therapy-services/:program_service_id/` |
| `POST` | Cancel an assigned assessment service | `/programs/program-services/assessment-services/:program_service_id/cancel/` |
| `POST` | Cancel an assigned therapy service | `/programs/program-services/therapy-services/:program_service_id/cancel/` |
| `POST` | Cancel an assigned consultation service | `/programs/program-services/consultation-services/:program_service_id/cancel/` |
| `GET` | List supported assessment providers | `/programs/program-services/assessment-services/:program_service_id/providers/` |
| `GET` | List supported assessment products | `/programs/program-services/assessment-services/:program_service_id/products/` |
| `GET`, `POST` | List or create assessment results | `/programs/program-services/assessment-services/:program_service_id/results/` |
| `GET` | List every assessment document | `/programs/program-services/assessment-services/:program_service_id/documents/` |
| `GET`, `PATCH`, `DELETE` | Retrieve, edit, or delete result metadata | `/programs/program-services/results/:result_id/` |
| `GET` | List result documents | `/programs/program-services/results/:result_id/documents/` |
| `DELETE` | Delete one result document | `/programs/program-result-documents/:document_id/` |

`program_service_id` is the UUID of `ProgramService`. It is not the UUID of the
nested catalogue `Service`.

The existing `/services/assessment-services/:service_id/*` and
`/services/therapy-services/:service_id/*` routes continue to use catalogue
service UUIDs and are outside this document's scope.

## 2. Access and Request Context

All endpoints require a valid JWT:

```http
Authorization: Bearer <access_token>
```

Access is allowed for administrators and associates. Customers cannot use
these endpoints.

`X-Center-ID` is required only for therapy cancellation. The selected center
must exist. Assessment and consultation cancellation do not require the
header. The endpoints do not apply center-assignment or feature-level RBAC
filtering.

The assessment and therapy ProgramService detail routes remain read-only.
Cancellation uses only the dedicated `POST` routes. Result and document
mutations remain available only through their dedicated routes. No route in
this document accepts `PUT`.

The complete assessment selection, result creation, and file-upload flow is
specified in `assessment-program-service-result-upload-frontend-eprd.md`.

## 3. Product Behavior

Use the category-specific endpoint corresponding to the assigned service:

- use the assessment endpoint when the nested service category code is
  `assessment`;
- use the therapy endpoint when the nested service category code is `therapy`.

Do not call one endpoint and fall back to the other after a `404`. A category
mismatch intentionally returns not found.

The response describes the assigned program-service line. The nested
`service` object contains only basic catalogue information. It does not include
centers, products, providers, or other nested relationships.

The API does not include the parent program. The frontend must retain the
program context from the page or query that supplied `program_service_id`.

## 4. Assessment Program Service Detail

### 4.1 Request

```http
GET /programs/program-services/assessment-services/:program_service_id/
Authorization: Bearer <access_token>
```

Request body:

```json
null
```

### 4.2 Success response

Status:

```text
200 OK
```

Body:

```json
{
  "detail": "Details.",
  "data": {
    "id": "<program_service_uuid>",
    "service": {
      "id": "<service_uuid>",
      "name": "Comprehensive Health Assessment",
      "service_category": "Assessment",
      "service_category_code": "assessment",
      "image": "<url|null>"
    },
    "assignment_type": "Standalone",
    "assignment_type_code": "standalone",
    "documents_count": 4,
    "created_date": "2026-08-07",
    "created_by": {
      "id": "<user_uuid>",
      "email": "admin@example.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": "<url|null>",
      "last_login": "<ISO-8601_datetime|null>"
    },
    "is_active": true,
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>",
    "cancellation_reason": null,
    "cancelled_by": null,
    "cancelled_at": null,
    "cancelled_date": null
  }
}
```

Only ProgramService rows whose nested service category is `assessment` resolve
through this endpoint.

`documents_count` is the server-maintained number of documents associated with
the assessment ProgramService. It is authoritative and can be `0`. The
frontend must not derive it from a locally loaded document preview or page.

## 5. Therapy Program Service Detail

### 5.1 Request

```http
GET /programs/program-services/therapy-services/:program_service_id/
Authorization: Bearer <access_token>
```

Request body:

```json
null
```

### 5.2 Success response

Status:

```text
200 OK
```

Body:

```json
{
  "detail": "Details.",
  "data": {
    "id": "<program_service_uuid>",
    "service": {
      "id": "<service_uuid>",
      "name": "Physiotherapy Session",
      "service_category": "Therapy",
      "service_category_code": "therapy",
      "image": "<url|null>"
    },
    "assignment_type": "Add On",
    "assignment_type_code": "add_on",
    "sessions_count": 12,
    "sessions_used": 3,
    "sessions_cancelled": 1,
    "redeem_code": "ABC123",
    "created_date": "2026-08-07",
    "created_by": {
      "id": "<user_uuid>",
      "email": "admin@example.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": "<url|null>",
      "last_login": "<ISO-8601_datetime|null>"
    },
    "is_active": true,
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>",
    "cancellation_reason": null,
    "cancelled_by": null,
    "cancelled_at": null,
    "cancelled_date": null
  }
}
```

Only ProgramService rows whose nested service category is `therapy` resolve
through this endpoint.

### 5.3 Therapy extension behavior

The therapy-only fields are sourced from the linked `TherapyProgramService`:

- `sessions_count` is the assigned session allowance;
- `sessions_used` is the number of redeemed sessions;
- `sessions_cancelled` is the number of cancelled sessions;
- `redeem_code` is the service-level redemption code.

When `sessions_count` is `0`, it means unlimited sessions. The frontend must
not render it as no sessions available.

The backend identifies the endpoint resource by ProgramService category only.
If legacy or inconsistent data has no linked therapy extension, all four
therapy-only fields are `null`:

```json
{
  "sessions_count": null,
  "sessions_used": null,
  "sessions_cancelled": null,
  "redeem_code": null
}
```

The frontend should show an unavailable-data state for these values rather
than converting them to zero.

## 6. Field Semantics

### 6.1 Identifiers

| Field | Meaning |
|---|---|
| `data.id` | ProgramService UUID used by these endpoints |
| `data.service.id` | Catalogue Service UUID used by `/services/*` APIs |

These identifiers are not interchangeable.

### 6.2 Assignment type

| Code | Display value | Meaning |
|---|---|---|
| `standalone` | `Standalone` | Service assigned as a standard program line |
| `add_on` | `Add On` | Service added beyond the original program/template allocation |

Use `assignment_type_code` for frontend logic and `assignment_type` for
display.

### 6.3 Lifecycle and cancellation

- `is_active: true` indicates an active assigned service.
- `is_active: false` indicates an inactive or cancelled assigned service.
- `cancellation_reason`, `cancelled_by`, `cancelled_at`, and `cancelled_date`
  can all be `null` when the service has not been cancelled.
- `created_by` can be `null` because the backend relationship is nullable.
- `cancelled_by` uses the same user shape as `created_by` when present.
- `created_date` and `cancelled_date` are date-only values in `YYYY-MM-DD`
  format.
- `created_at`, `updated_at`, `cancelled_at`, and `last_login` are ISO-8601
  datetimes.

The detail endpoints do not perform cancellation or redemption.

### 6.4 Cancellation

All three cancellation endpoints accept the same optional request fields:

```json
{
  "cancellation_reason": "Cancelled at the customer's request.",
  "cancelled_date": "2026-08-12"
}
```

`cancellation_reason` accepts a string, blank string, or `null`.
`cancelled_date` defaults to the backend's current local date when omitted and
does not accept `null`.

A successful request returns `201 Created`:

```json
{
  "detail": "Create success.",
  "data": {
    "cancellation_reason": "Cancelled at the customer's request.",
    "cancelled_by": {
      "id": "<user_uuid>",
      "email": "<email|null>",
      "first_name": "<string>",
      "last_name": "<string>",
      "image": "<url|null>",
      "last_login": "<ISO-8601_datetime|null>"
    },
    "cancelled_at": "<ISO-8601_datetime>",
    "cancelled_date": "2026-08-12"
  }
}
```

Cancellation sets only the assigned `ProgramService.is_active` flag to
`false`. Existing assessment results and documents keep their current rows,
files, metadata, counters, and active flags. Existing inactive-service gates
prevent new results and documents, while current edit and delete behavior is
unchanged.

## 7. Recommended Frontend Contracts

```ts
type ServiceCategoryCode = "assessment" | "therapy";
type ServiceAssignmentTypeCode = "standalone" | "add_on";

interface BaseUser {
  id: string;
  email: string | null;
  first_name: string;
  last_name: string;
  image: string | null;
  last_login: string | null;
}

interface BasicService {
  id: string;
  name: string;
  service_category: "Assessment" | "Therapy";
  service_category_code: ServiceCategoryCode;
  image: string | null;
}

interface ProgramServiceDetailBase {
  id: string;
  service: BasicService;
  assignment_type: "Standalone" | "Add On";
  assignment_type_code: ServiceAssignmentTypeCode;
  created_date: string;
  created_by: BaseUser | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  cancellation_reason: string | null;
  cancelled_by: BaseUser | null;
  cancelled_at: string | null;
  cancelled_date: string | null;
}

interface AssessmentProgramServiceDetail extends ProgramServiceDetailBase {
  service: BasicService & {
    service_category: "Assessment";
    service_category_code: "assessment";
  };
  documents_count: number;
}

interface TherapyProgramServiceDetail extends ProgramServiceDetailBase {
  service: BasicService & {
    service_category: "Therapy";
    service_category_code: "therapy";
  };
  sessions_count: number | null;
  sessions_used: number | null;
  sessions_cancelled: number | null;
  redeem_code: string | null;
}

interface DetailResponse<T> {
  detail: "Details.";
  data: T;
}

interface ProgramServiceCancelPayload {
  cancellation_reason?: string | null;
  cancelled_date?: string;
}

interface ProgramServiceCancellation {
  cancellation_reason: string | null;
  cancelled_by: BaseUser;
  cancelled_at: string;
  cancelled_date: string;
}

interface CancelResponse {
  detail: "Create success.";
  data: ProgramServiceCancellation;
}

interface APIErrorResponse {
  detail: string | Record<string, string | string[]>;
}
```

Although these TypeScript contracts share a frontend base interface for
convenience, the backend assessment and therapy serializers are independent.

## 8. Error Handling

Errors do not contain a `data` property.

### 8.1 Invalid or mismatched ID

An unknown ProgramService UUID, a catalogue Service UUID, or a ProgramService
whose category does not match the selected endpoint returns:

```text
404 Not Found
```

```json
{
  "detail": "<not_found_message>"
}
```

Treat all three cases as program service not found. Do not expose whether a
ProgramService exists under another category.

### 8.2 Authentication and authorization

| Status | Meaning | Frontend behavior |
|---|---|---|
| `401` | JWT is absent, expired, or invalid | Start the authentication recovery flow |
| `403` | Authenticated account is neither an administrator nor an associate | Show access denied |
| `404` | ProgramService is absent or belongs to another category | Show program service not found |
| `405` | An unsupported method was used | Treat as a frontend integration error |
| `500` | Unexpected server error | Show the standard retryable error state |

## 9. State and Cache Rules

- Include both category and ProgramService UUID in the detail query key.
- Do not use the nested catalogue Service UUID as the ProgramService cache key.
- Do not optimistically mutate cancellation audit fields.
- Invalidate or refetch the relevant detail query after successful
  cancellation or therapy redemption.
- Do not calculate cancellation state solely from nullable cancellation
  fields; use `is_active` as the primary lifecycle flag.
- Do not derive remaining therapy sessions when `sessions_count` is `0`, since
  zero represents unlimited sessions.
- Keep `null` therapy-extension values distinct from numeric zero.

## 10. Acceptance Criteria

- The frontend calls the assessment endpoint with a ProgramService UUID for an
  assessment-category assigned service.
- The frontend calls the therapy endpoint with a ProgramService UUID for a
  therapy-category assigned service.
- Catalogue Service UUIDs are never passed to these endpoints.
- Category mismatches produce the program-service-not-found state without
  endpoint fallback.
- Both pages render the shallow nested service, assignment type, lifecycle,
  cancellation, and audit information.
- Assessment renders `documents_count`; therapy does not receive that field.
- Therapy additionally renders session counters and the redemption code.
- Unlimited therapy sessions are handled when `sessions_count` is `0`.
- Missing therapy-extension values render as unavailable rather than zero.
- The UI does not require or send `X-Center-ID` for detail requests.
- Therapy cancellation sends a selected `X-Center-ID`; assessment and
  consultation cancellation do not.
- Successful cancellation refetches the relevant detail and renders the
  returned audit fields.
- Existing assessment results and documents remain visible after cancellation.
- Customers do not receive access to these detail experiences.
- No edit, delete, cancel, or redeem operation is sent to either detail URL.
- Cache keys distinguish assessment and therapy resources even when UUID input
  is reused accidentally.

## 11. Result Metadata Workflow

The frontend must create a result before documents can be associated with it:

1. Select an active provider and product through the ProgramService endpoints.
2. Retrieve the product's allowed document types.
3. `POST` result metadata under the assessment ProgramService.
4. Read `data.id` from the creation response.
5. Upload files one by one with only file and category data.
6. Refetch the result and ProgramService detail after document mutations.

`ServiceResult` has no name. A result can exist without documents. Every file
keeps its own filename on `ServiceDocument`.

Result creation is rejected when the ProgramService is inactive.

## 12. Assessment Result Collection

### 12.1 Create metadata

```http
POST /programs/program-services/assessment-services/:program_service_id/results/
Authorization: Bearer <access_token>
Content-Type: application/json
```

`product_id` and `document_type` are required and cannot be null. Dates are
optional and nullable:

```json
{
  "product_id": "<product_uuid>",
  "document_type": "dxa_core_scan",
  "sample_collection_date": "2026-08-01",
  "report_generation_date": "2026-08-07"
}
```

`product_id` must identify an active product with an active provider and active
assignment to the nested catalogue service. `document_type` must be returned by
the selected product's allowed-document endpoint. The backend validates this
pair and snapshots the product and provider names.

`result_mode` is always `upload` and cannot be submitted by the frontend.
There is no ordering validation between the two dates.

Success:

```text
201 Created
```

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<result_uuid>",
    "product": {
      "id": "<product_uuid>",
      "name": "DXA Core Scan",
      "code": "<product_code>"
    },
    "provider_name": "<provider_name>",
    "product_name": "<product_name>",
    "result_mode": "Upload",
    "result_mode_code": "upload",
    "document_type": "Core Scan",
    "document_type_code": "dxa_core_scan",
    "sample_collection_date": "2026-08-01",
    "report_generation_date": "2026-08-07",
    "created_by": {
      "id": "<user_uuid>",
      "email": "admin@example.com",
      "first_name": "Admin",
      "last_name": "User",
      "image": null,
      "last_login": "<ISO-8601_datetime|null>"
    },
    "is_active": true,
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>"
  }
}
```

### 12.2 List results

```http
GET /programs/program-services/assessment-services/:program_service_id/results/
Authorization: Bearer <access_token>
```

Query parameters:

| Parameter | Meaning |
|---|---|
| `page` | Page number |
| `limit` | Page size, maximum 50 |
| `product` | Exact product UUID |

Results are ordered newest first. Each result contains the result metadata plus
the annotated `documents_count`.

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "<result_uuid>",
      "product": "<BasicProduct>",
      "provider_name": "<provider_name>",
      "product_name": "<product_name>",
      "result_mode": "Upload",
      "result_mode_code": "upload",
      "document_type": "Core Scan",
      "document_type_code": "dxa_core_scan",
      "sample_collection_date": null,
      "report_generation_date": null,
      "documents_count": 0,
      "created_by": "<BaseUser|null>",
      "is_active": true,
      "created_at": "<ISO-8601_datetime>",
      "updated_at": "<ISO-8601_datetime>"
    }
  ]
}
```

## 13. Result Detail, Editing, and Deletion

### 13.1 Retrieve

```http
GET /programs/program-services/results/:result_id/
Authorization: Bearer <access_token>
```

Returns the complete result shape with `detail: "Details."`.

### 13.2 Edit metadata

```http
PATCH /programs/program-services/results/:result_id/
Authorization: Bearer <access_token>
Content-Type: application/json
```

Before the first document is uploaded, the request can correct the product,
document type, or either date:

```json
{
  "product_id": "<product_uuid>",
  "document_type": "other",
  "sample_collection_date": null,
  "report_generation_date": "2026-08-08"
}
```

Changing the product refreshes the product/provider snapshots and validates the
resulting product/type pair. Once any document exists, product and type changes
return `400`; date edits remain available. Result mode, ownership, creator,
active state, and document count are read-only.

Success returns `200 OK`, `detail: "Updated successfully."`, and the complete
updated result.

### 13.3 Delete result

```http
DELETE /programs/program-services/results/:result_id/
Authorization: Bearer <access_token>
```

Success:

```text
200 OK
```

```json
{
  "detail": "Deleted successfully."
}
```

Deletion is permanent. Every linked document row and stored file is deleted,
and the ProgramService `documents_count` is recomputed.

## 14. List Documents for One Result

```http
GET /programs/program-services/results/:result_id/documents/
Authorization: Bearer <access_token>
```

Query parameters:

| Parameter | Meaning |
|---|---|
| `page` | Page number |
| `limit` | Page size, maximum 50 |
| `document_type` | Exact type code inherited from the parent result |
| `document_category` | `report` or `raw` |
| `search` | Case-insensitive filename substring |

The response is paginated and returns the document shape shown above.

## 15. ProgramService-Wide Document List

```http
GET /programs/program-services/assessment-services/:program_service_id/documents/
Authorization: Bearer <access_token>
```

This is the authoritative collection of every document across every result
belonging to the assessment ProgramService.

It accepts the result-document filters plus:

| Parameter | Meaning |
|---|---|
| `result` | Exact result UUID |

The response is paginated and includes the shallow nested result so documents
from different results remain distinguishable.

## 16. Delete One Document

```http
DELETE /programs/program-result-documents/:document_id/
Authorization: Bearer <access_token>
```

The document is resolved directly by its UUID. Its parent result and
ProgramService are derived from the resolved document instance.

Success:

```json
{
  "detail": "Deleted successfully."
}
```

Deletion permanently removes the database row and stored file, then
recomputes ProgramService `documents_count`.

## 17. Frontend Result and Document Contracts

```ts
interface BasicProduct {
  id: string;
  name: string;
  code: string;
}

interface AssessmentServiceResult {
  id: string;
  product: BasicProduct | null;
  provider_name: string | null;
  product_name: string | null;
  result_mode: "Upload";
  result_mode_code: "upload";
  document_type: string;
  document_type_code: string;
  sample_collection_date: string | null;
  report_generation_date: string | null;
  documents_count: number;
  created_by: BaseUser | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface BasicAssessmentServiceResult {
  id: string;
  provider_name: string | null;
  product_name: string | null;
  result_mode: "Upload";
  result_mode_code: "upload";
  document_type: string;
  document_type_code: string;
  sample_collection_date: string | null;
  report_generation_date: string | null;
}

interface AssessmentServiceDocument {
  id: string;
  result: BasicAssessmentServiceResult;
  file: string;
  filename: string;
  content_type: string;
  document_category: "Report file" | "Raw data file";
  document_category_code: "report" | "raw";
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface ResultCreatePayload {
  product_id: string;
  document_type: string;
  sample_collection_date?: string | null;
  report_generation_date?: string | null;
}

interface ResultPatchPayload {
  product_id?: string;
  document_type?: string;
  sample_collection_date?: string | null;
  report_generation_date?: string | null;
}
```

## 18. Result and Document State Rules

- Key result queries by `result_id` and result collections by
  `program_service_id` plus filters.
- Key document collections separately for ProgramService-wide and
  result-specific routes.
- After document deletion, invalidate the result detail, both applicable
  document lists, and assessment ProgramService detail.
- After result deletion, remove its detail cache and invalidate the result
  list, ProgramService document list, and ProgramService detail.
- Treat `documents_count` from the API as authoritative; never derive it from
  the current paginated page.
- Do not optimistically remove files because storage/database deletion must
  complete first.
- A `404` can mean an unknown ID, category mismatch, or nested ownership
  mismatch. Present one not-found state without probing other endpoints.
