# Frontend API PRD: Customer Therapy Programs

## 1. Objective

Provide a profile-scoped frontend experience for:

- Listing therapy programs assigned to a customer profile.
- Filtering programs by active, completion, and expiry state.
- Creating a therapy program for a customer profile as an admin or associate.
- Displaying summary counts plus previews of up to three services and three redeemable centers.

The customer profile is identified by the URL. Do not send `profile_id` in the request payload.

## 2. Endpoint

```text
<baseURL>/profiles/<profile_uuid>/programs/therapy-programs/
```

### Required headers

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

`X-Center-ID` is not used by this endpoint. The owning center is submitted as `center_id` in the POST payload.

### Access

| Method | Admin | Associate | Customer |
|---|---:|---:|---:|
| `GET` | Allowed | Allowed | Allowed for a profile owned by the authenticated customer |
| `POST` | Allowed | Allowed when actively assigned to the submitted center | Not allowed |

Admins and associates receive `403 Forbidden` if their account type is not allowed. Customers receive `403 Forbidden` for POST requests.

## 3. Therapy Program Response Object

Both GET list entries and the POST response use this object structure.

```json
{
  "id": "<program_uuid>",
  "program_type": "therapy",
  "notes": "<string|null>",
  "expires_at": "<YYYY-MM-DD>",
  "is_complimentary": "<boolean>",
  "price": "<decimal_string|null>",
  "services_count": "<integer>",
  "sessions_count": "<integer>",
  "sessions_cancelled": "<integer>",
  "sessions_used": "<integer>",
  "redeemable_centers": [
    {
      "id": "<center_uuid>",
      "code": "<string>",
      "name": "<string>",
      "image": "<url|null>",
      "address": "<string|null>",
      "address_line_1": "<string|null>",
      "address_line_2": "<string|null>",
      "city": "<string|null>",
      "state": "<string|null>",
      "country": "<string|null>",
      "pincode": "<string|null>",
      "staff_count": "<integer>",
      "inactive_staff_count": "<integer>",
      "customer_count": "<integer>",
      "inactive_customer_count": "<integer>",
      "is_active": "<boolean>",
      "created_at": "<datetime>",
      "updated_at": "<datetime>"
    }
  ],
  "redeemable_centers_count": "<integer>",
  "services": [
    {
      "id": "<program_service_uuid>",
      "service": {
        "id": "<service_uuid>",
        "name": "<string>",
        "service_category": "<display_label>",
        "service_category_code": "<therapy|assessment|consultation>",
        "image": "<url|null>"
      },
      "sessions_count": "<integer>",
      "sessions_used": "<integer>",
      "sessions_cancelled": "<integer>",
      "redeem_code": "<string>",
      "created_at": "<datetime>",
      "is_active": "<boolean>",
      "can_redeem": "<boolean>",
      "cancellation_reason": "<string|null>",
      "cancelled_by": {
        "id": "<user_uuid>",
        "email": "<string|null>",
        "first_name": "<string>",
        "last_name": "<string>",
        "image": "<url|null>",
        "last_login": "<datetime|null>"
      },
      "cancelled_at": "<datetime|null>"
    }
  ],
  "created_date": "<YYYY-MM-DD>",
  "cancelled_date": "<YYYY-MM-DD|null>",
  "created_at": "<datetime>",
  "updated_at": "<datetime>",
  "is_active": "<boolean>",
  "created_by": {
    "id": "<user_uuid>",
    "email": "<string|null>",
    "first_name": "<string>",
    "last_name": "<string>",
    "image": "<url|null>",
    "last_login": "<datetime|null>"
  }
}
```

`cancelled_by` and `created_by` may be `null` for historical records where the referenced user is unavailable.

### Preview behavior

- `services` contains at most three services.
- `services_count` contains the total number of assigned services.
- `redeemable_centers` contains at most three centers.
- `redeemable_centers_count` contains the total number of redeemable centers.
- Do not assume the preview arrays contain every related record when their count is greater than three.

## 4. GET Therapy Programs

### URL

```text
<baseURL>/profiles/<profile_uuid>/programs/therapy-programs/?page=<page>&limit=<limit>&active=<0|1>&complete=<0|1>&expired=<0|1>
```

### Query parameters

| Parameter | Type | Required | Behavior |
|---|---|---:|---|
| `page` | Integer | No | Page number. Defaults to the first page. |
| `limit` | Integer | No | Items per page. Defaults to 10 and is capped at 50. |
| `active` | `0` or `1` | No | `1` returns active programs; `0` returns inactive programs. |
| `complete` | `0` or `1` | No | `1` returns programs where total sessions equal used plus cancelled sessions. |
| `expired` | `0` or `1` | No | `1` returns programs expiring before today; `0` returns programs expiring today or later. |

Filters are combined with AND semantics. Unsupported filter values are ignored. This endpoint does not support a `search` parameter.

### Request payload

```json
null
```

### Success response — `200 OK`

```json
{
  "detail": "All data.",
  "count": "<integer>",
  "next": "<url|null>",
  "previous": "<url|null>",
  "data": [
    "<TherapyProgramResponse>"
  ]
}
```

An empty result is returned as:

```json
{
  "detail": "All data.",
  "count": 0,
  "next": null,
  "previous": null,
  "data": []
}
```

Treat `next` and `previous` as opaque URLs supplied by the API.

## 5. POST Therapy Program

### URL

```text
<baseURL>/profiles/<profile_uuid>/programs/therapy-programs/
```

### Request payload

```json
{
  "center_id": "<center_uuid>",
  "expires_at": "<YYYY-MM-DD>",
  "is_complimentary": false,
  "price": "2500.00",
  "notes": "Complete two sessions each week.",
  "add_services": [
    {
      "id": "<service_uuid>",
      "sessions_count": 8
    }
  ],
  "add_redeemable_centers": [
    {
      "id": "<center_uuid>"
    }
  ],
  "created_date": "<YYYY-MM-DD>"
}
```

### Request fields

| Field | Type | Required | Rules |
|---|---|---:|---|
| `center_id` | UUID | Yes | Must identify an active center. Associates must have an active assignment to it. |
| `expires_at` | Date | Yes | Must be today or a future date. |
| `is_complimentary` | Boolean | No | Defaults to `true`. |
| `price` | Decimal string or number | Conditional | Required when `is_complimentary` is `false`; may be `null` otherwise. |
| `notes` | String or null | No | May be omitted, blank, or null. |
| `add_services` | Array | Yes | Must contain at least one service. |
| `add_services[].id` | UUID | Yes | Must identify an existing service. |
| `add_services[].sessions_count` | Integer | Yes | Minimum value is 1. |
| `add_redeemable_centers` | Array | No | May be omitted or empty. Each center must be linked to the URL's customer profile. |
| `add_redeemable_centers[].id` | UUID | Yes | Center identifier. |
| `created_date` | Date | No | Uses the backend default when omitted. |
| `cancelled_date` | Date | No | Generally omit for a newly created program. If supplied, it must be `YYYY-MM-DD`, not `null`. |

The owning center does not have to be included in `add_redeemable_centers`.

Do not submit these response-only fields:

- `id`
- `program_type`
- `services`
- `services_count`
- `sessions_count`
- `sessions_used`
- `sessions_cancelled`
- `redeemable_centers`
- `redeemable_centers_count`
- `created_at`
- `updated_at`
- `is_active`
- `created_by`

Do not submit `profile_id`; the profile UUID comes from the URL.

### Complimentary example

```json
{
  "center_id": "018f7df4-1e9a-7772-9f5e-8c5f7720b901",
  "expires_at": "2026-12-31",
  "is_complimentary": true,
  "price": null,
  "notes": "Complimentary recovery program.",
  "add_services": [
    {
      "id": "018f7df4-1e9a-7772-9f5e-8c5f7720b902",
      "sessions_count": 6
    }
  ]
}
```

### Success response — `201 Created`

```json
{
  "detail": "Create success.",
  "data": "<TherapyProgramResponse>"
}
```

`program_type` is always returned as `therapy` and cannot be selected by the frontend.

### Duplicate services

The backend deduplicates repeated service IDs. If the same service appears multiple times, the final submitted `sessions_count` is used. The frontend should prevent duplicate selections so the request remains unambiguous.

## 6. Error Responses

The API does not include a `success` field. Errors use a top-level `detail` value.

### Field validation — `400 Bad Request`

```json
{
  "detail": {
    "expires_at": "Expiry date cannot be earlier than today's date."
  }
}
```

Other possible field keys include:

- `center_id`
- `price`
- `add_services`
- `add_redeemable_centers`

Serializer-level errors can contain arrays and nested objects. For example:

```json
{
  "detail": {
    "add_services": [
      {
        "sessions_count": [
          "Ensure this value is greater than or equal to 1."
        ]
      }
    ]
  }
}
```

The frontend error normalizer must therefore support string, array, and nested-object values inside `detail`.

### Profile not found or inaccessible — `404 Not Found`

```json
{
  "detail": "Customer profile with this ID not found."
}
```

### Authentication failure — `401 Unauthorized`

```json
{
  "detail": "<authentication_error>"
}
```

### Permission failure — `403 Forbidden`

```json
{
  "detail": "<permission_error>"
}
```

## 7. Frontend Requirements

### List screen

- Load programs using the profile UUID from the current route or selected profile context.
- Support active, complete, and expired filters using `0` and `1` query values.
- Use `count` for the total result count and `next`/`previous` for pagination state.
- Display the returned service and redeemable-center arrays as previews.
- Show the corresponding count when additional hidden records exist.
- Render `price` as currency using decimal-safe handling; do not parse it through binary floating-point for calculations.
- Render dates as local display dates without changing their calendar day.

### Creation form

- Show creation controls only to admins and associates.
- Require an owning center, expiry date, and at least one service.
- Show `price` as required when complimentary mode is disabled.
- Prevent duplicate service selections.
- Allow zero additional redeemable centers.
- Submit only service IDs and session counts, not complete service objects.
- Submit only center IDs in `add_redeemable_centers`.
- On success, invalidate/refetch the list or insert the returned response object.
- Display backend validation messages beside their corresponding fields.

## 8. Acceptance Criteria

- A customer can list programs only for one of their own profile UUIDs.
- A customer never sees the creation action and cannot successfully POST.
- An admin can create a program using any active center ID.
- An associate can create only when actively assigned to the submitted center.
- The form blocks submission without a service or without a price for a paid program.
- Past expiry dates are rejected and their backend message is displayed.
- Omitting `add_redeemable_centers` produces a valid request.
- List filters serialize booleans as `0` or `1`.
- Pagination uses the API's `count`, `next`, `previous`, and `data` fields.
- Program cards do not treat the three-item previews as complete related lists.
