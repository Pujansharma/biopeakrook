# Program and Program Service Cancellation — Frontend ePRD

## 1. Purpose

Implement cancellation for assigned assessment, therapy, and consultation
services, and for a complete composite program. This document covers only the
cancellation endpoints and their request and response payloads.

## 2. Endpoints

| Resource | Method | Endpoint |
|---|---|---|
| Assessment ProgramService | `POST` | `/programs/program-services/assessment-services/:program_service_id/cancel/` |
| Therapy ProgramService | `POST` | `/programs/program-services/therapy-services/:program_service_id/cancel/` |
| Consultation ProgramService | `POST` | `/programs/program-services/consultation-services/:program_service_id/cancel/` |
| Composite program | `POST` | `/programs/composites/programs/:program_id/cancel/` |

`program_service_id` is the UUID of the assigned `ProgramService`, not the UUID
of the catalogue service.

`program_id` on the composite route is the UUID of `CompositeProgram`, which is
also the primary key of its related `Program`.

All requests require a valid JWT. ProgramService cancellation is available to
administrators and associates. Composite-program cancellation is available to
administrators and associates granted the packages permission.

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

Therapy ProgramService and composite-program cancellation require an existing
center UUID:

```http
X-Center-ID: <center_uuid>
```

For composite cancellation, the program must be owned by or redeemable at the
selected center. Do not send or require `X-Center-ID` for assessment or
consultation ProgramService cancellation.

## 3. Request Payload

All four endpoints use the same payload:

```json
{
  "cancellation_reason": "Cancelled at the customer's request.",
  "cancelled_date": "2026-08-12"
}
```

| Field | Required | Type | Rules |
|---|---|---|---|
| `cancellation_reason` | No | `string \| null` | Accepts text, an empty string, or `null` |
| `cancelled_date` | No | `YYYY-MM-DD` string | Defaults to the backend's current local date when omitted; `null` is invalid |

The backend does not restrict `cancelled_date` to today or an earlier date.

An empty payload is valid:

```json
{}
```

The frontend contract is:

```ts
interface ProgramServiceCancelPayload {
  cancellation_reason?: string | null;
  cancelled_date?: string;
}

type CompositeProgramCancelPayload = ProgramServiceCancelPayload;
```

## 4. Success Response

A successful cancellation returns `201 Created`:

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

```ts
interface BaseUser {
  id: string;
  email: string | null;
  first_name: string;
  last_name: string;
  image: string | null;
  last_login: string | null;
}

interface ProgramServiceCancellation {
  cancellation_reason: string | null;
  cancelled_by: BaseUser;
  cancelled_at: string;
  cancelled_date: string;
}

interface ProgramServiceCancelResponse {
  detail: "Create success.";
  data: ProgramServiceCancellation;
}

interface CompositeProgramCancellation {
  cancellation_reason: string | null;
  cancelled_by: BaseUser;
  cancelled_at: string | null;
  cancelled_date: string;
}

interface CompositeProgramCancelResponse {
  detail: "Create success.";
  data: CompositeProgramCancellation;
}
```

After success, treat the assigned service as inactive. Cancellation does not
deactivate or alter existing assessment result or document records.

After composite-program cancellation, treat the composite program, its parent
program, and its active therapy ProgramServices as inactive. The composite
response can return `cancelled_at: null` when there were no active therapy
ProgramServices to cancel.

## 5. Error Responses

Errors use the standard response envelope and do not include `data`:

```json
{
  "detail": "<error_message>"
}
```

| Status | Condition |
|---|---|
| `400` | The service is already cancelled |
| `400` | A therapy service has already been fully used |
| `400` | Therapy ProgramService or composite-program cancellation omits `X-Center-ID` |
| `400` | The composite program is already cancelled |
| `400` | A request field fails validation |
| `401` | Authentication is missing or invalid |
| `403` | The authenticated user lacks access to the requested cancellation |
| `404` | The ProgramService does not exist or belongs to another category |
| `404` | The required `X-Center-ID` does not identify an existing center |
| `404` | The composite program does not exist or is unavailable at the selected center |

Do not retry an already-cancelled request. Refetch the owning screen's data so
the UI reflects the server state.

## 6. Frontend Behavior

- Show cancellation only for an active assigned service.
- Require explicit confirmation before submitting.
- Allow the reason to be blank and the date to be omitted.
- Include the selected center header for therapy ProgramService and composite-
  program cancellation only.
- Disable repeated submission while the request is pending.
- After success, close the cancellation flow and refetch the owning screen's
  program or service data.
- If the service is already cancelled, refetch instead of presenting another
  cancellation attempt.

## 7. Acceptance Criteria

- The frontend selects the endpoint from the service category and sends the
  ProgramService UUID.
- Assessment and consultation cancellation succeed without `X-Center-ID`.
- Therapy cancellation sends a valid `X-Center-ID`.
- Composite-program cancellation calls
  `/programs/composites/programs/:program_id/cancel/` with its
  `CompositeProgram` UUID and a valid `X-Center-ID`.
- An empty payload is accepted and uses the backend cancellation date default.
- A supplied reason and date are returned in the cancellation audit response.
- Unknown IDs and category mismatches produce the same not-found UI state.
- The UI prevents accidental duplicate submission and refreshes server state
  after success or an already-cancelled response.
