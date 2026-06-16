# External Therapy API

External therapy endpoints are unauthenticated. They identify the customer by the
`phone` query parameter and return data only for that customer.

Base response format:

```json
{
  "detail": "All data.",
  "data": {}
}
```

Paginated list responses include `count`, `next`, and `previous` at the root:

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": []
}
```

Use E.164 phone numbers in examples unless the caller is already using another
accepted phone format.

## GET customer-therapy-programs/

Lists therapy programs for a customer.

Authentication: Not required.

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |
| `active` | No | `1` for active programs, `0` for inactive programs. |
| `complete` | No | `1` for complete programs, `0` for incomplete programs. |
| `expired` | No | `1` for expired programs, `0` for non-expired programs. |

Sample request:

```http
GET /external/customer-therapy-programs/?phone=%2B919876543210&active=1
```

Sample response:

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "018f7df4-1e9a-7772-9f5e-8c5f7720b901",
      "program_type": "Therapy",
      "expires_at": "2026-12-31",
      "services_count": 2,
      "sessions_count": 12,
      "sessions_used": 4,
      "sessions_cancelled": 0,
      "created_date": "2026-06-01",
      "cancelled_date": null,
      "created_at": "2026-06-01T10:15:00+05:30",
      "updated_at": "2026-06-10T12:30:00+05:30",
      "is_active": true
    }
  ]
}
```

## GET customer-therapy-programs/summary/

Returns therapy program summary counts for a customer profile.

Authentication: Not required.

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |

Sample request:

```http
GET /external/customer-therapy-programs/summary/?phone=%2B919876543210
```

Sample response:

```json
{
  "detail": "Details.",
  "data": {
    "id": "018f7df2-0d88-7a7a-80f1-f3f43fd7f021",
    "first_name": "Aarav",
    "last_name": "Mehta",
    "programs_count": 3,
    "programs_expired": 1,
    "programs_inactive": 0,
    "programs_complete": 1,
    "sessions_count": 24,
    "sessions_used": 10,
    "sessions_cancelled": 2,
    "sessions_expired": 4,
    "centers_count": 1,
    "external_centers_count": 2
  }
}
```

## GET customer-therapy-programs/:program_id/

Returns one therapy program.

Authentication: Not required.

Path parameters:

| Name | Description |
|---|---|
| `program_id` | Therapy program UUID. |

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |

Sample request:

```http
GET /external/customer-therapy-programs/018f7df4-1e9a-7772-9f5e-8c5f7720b901/?phone=%2B919876543210
```

Sample response:

```json
{
  "detail": "Details.",
  "data": {
    "id": "018f7df4-1e9a-7772-9f5e-8c5f7720b901",
    "program_type": "Therapy",
    "is_complimentary": true,
    "price": null,
    "expires_at": "2026-12-31",
    "sessions_count": 12,
    "sessions_used": 4,
    "services_count": 2,
    "created_date": "2026-06-01",
    "created_at": "2026-06-01T10:15:00+05:30",
    "updated_at": "2026-06-10T12:30:00+05:30",
    "is_active": true,
    "cancellation_reason": null,
    "cancelled_at": null,
    "cancelled_date": null
  }
}
```

## GET customer-therapy-programs/:program_id/services/

Lists therapy services assigned to one therapy program. The resource root is
`TherapyProgramService`; `ProgramService` is an internal bridge only.

Authentication: Not required.

Path parameters:

| Name | Description |
|---|---|
| `program_id` | Therapy program UUID. |

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |

Sample request:

```http
GET /external/customer-therapy-programs/018f7df4-1e9a-7772-9f5e-8c5f7720b901/services/?phone=%2B919876543210
```

Sample response:

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "018f7df5-5b24-7a65-9b42-df00a7ff1100",
      "service": {
        "id": "018f7df5-0b95-72c1-8625-355cb24f3f70",
        "name": "Physiotherapy Session",
        "centers": [
          {
            "id": "018f7df1-8e57-7f12-95ec-c4fadc78e800",
            "code": "BN-MUM-001",
            "name": "Biopeak Mumbai"
          }
        ]
      },
      "sessions_count": 6,
      "sessions_used": 2,
      "redeem_code": "A7K3P9",
      "created_date": "2026-06-01",
      "created_at": "2026-06-01T10:15:05+05:30",
      "is_active": true,
      "cancelled_at": null,
      "cancelled_date": null
    }
  ]
}
```

## GET customer-therapy-services/:service_id/

Returns one therapy service assigned to a customer's therapy program. The
`service_id` is the `TherapyProgramService` UUID.

Authentication: Not required.

Path parameters:

| Name | Description |
|---|---|
| `service_id` | Therapy program service UUID. |

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |

Sample request:

```http
GET /external/customer-therapy-services/018f7df5-5b24-7a65-9b42-df00a7ff1100/?phone=%2B919876543210
```

Sample response:

```json
{
  "detail": "Details.",
  "data": {
    "program": {
      "id": "018f7df4-1e9a-7772-9f5e-8c5f7720b901",
      "program_type": "Therapy",
      "is_complimentary": true,
      "price": null,
      "expires_at": "2026-12-31",
      "sessions_count": 12,
      "sessions_used": 4,
      "services_count": 2,
      "created_date": "2026-06-01",
      "created_at": "2026-06-01T10:15:00+05:30",
      "updated_at": "2026-06-10T12:30:00+05:30",
      "is_active": true,
      "cancellation_reason": null,
      "cancelled_at": null,
      "cancelled_date": null
    },
    "service": {
      "id": "018f7df5-0b95-72c1-8625-355cb24f3f70",
      "name": "Physiotherapy Session",
      "centers": [
        {
          "id": "018f7df1-8e57-7f12-95ec-c4fadc78e800",
          "code": "BN-MUM-001",
          "name": "Biopeak Mumbai"
        }
      ]
    },
    "sessions_count": 6,
    "sessions_used": 2,
    "redeem_code": "A7K3P9",
    "created_date": "2026-06-01",
    "created_at": "2026-06-01T10:15:05+05:30",
    "is_active": true,
    "cancellation_reason": null,
    "cancelled_at": null,
    "cancelled_date": null
  }
}
```

## GET customer-therapy-services/:service_id/redemption-history/

Lists redemption history rows for one therapy program service.

Authentication: Not required.

Path parameters:

| Name | Description |
|---|---|
| `service_id` | Therapy program service UUID. |

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |

Sample request:

```http
GET /external/customer-therapy-services/018f7df5-5b24-7a65-9b42-df00a7ff1100/redemption-history/?phone=%2B919876543210
```

Sample response:

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "018f7df8-70f7-746c-a982-e2f20f1ed100",
      "redemption_type": "redeem",
      "redeem_center": {
        "id": "018f7df1-8e57-7f12-95ec-c4fadc78e800",
        "code": "BN-MUM-001",
        "name": "Biopeak Mumbai"
      },
      "redeemed_date": "2026-06-10",
      "redeemed_at": "2026-06-10T12:30:00+05:30",
      "quantity": 1,
      "redeemed_by": {
        "id": "018f7df0-7005-7241-b150-c853b511f300",
        "email": "associate@example.com",
        "first_name": "Nisha",
        "last_name": "Rao",
        "image": null,
        "last_login": "2026-06-10T09:00:00+05:30"
      }
    }
  ]
}
```

## GET customer-associates/

Lists associates linked to an external customer profile.

Authentication: Not required.

Query parameters:

| Name | Required | Description |
|---|---:|---|
| `phone` | Yes | Customer phone number used for lookup. |

Sample request:

```http
GET /external/customer-associates/?phone=%2B919876543210
```

Sample response:

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "018f7df0-7005-7241-b150-c853b511f300",
      "email": "associate@example.com",
      "contact_phone": "+919812345678",
      "first_name": "Nisha",
      "last_name": "Rao",
      "gender": "Female",
      "image": null,
      "role": {
        "id": "018f7df0-f821-78e3-a39f-e39bd3fc5500",
        "name": "Physiotherapist",
        "role_tag": "physiotherapist",
        "is_system": false,
        "is_active": true,
        "created_at": "2026-05-15T09:00:00+05:30",
        "updated_at": "2026-05-15T09:00:00+05:30"
      },
      "title": "Dr.",
      "description": "Senior physiotherapy specialist.",
      "tagline": "Movement and recovery care",
      "experience": 8.5,
      "qualifications": [
        "MPT",
        "BPT"
      ],
      "professions": [
        "Physiotherapist"
      ],
      "has_verified_badge": true
    }
  ]
}
```
