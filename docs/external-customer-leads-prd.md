# PRD: External Customer Lead Detail API

## Overview

The External Customer Lead Detail API exposes one customer lead record to an external caller by using the customer's phone number as the lookup key.

Endpoint:

```http
GET /external/customer-leads/?phone=%2B91-9999911118
```

Current implementation:

- URL route: `external/urls.py`
- View: `CustomerLeadDetailView`
- Serializer: `ExternalCustomerLeadSerializer`
- Model: `leads.models.Lead`

## Objective

Provide external systems with a read-only customer lead detail lookup that returns lead identity, conversion state, selected packages, home center, and linked customer profile information for a known customer phone number.

## Users

Primary users:

- External client applications that need to verify whether a lead exists for a phone number.
- External customer-facing applications that need lead and joined-customer state before showing program, onboarding, or center-specific experiences.

Internal users:

- Biopeak operations and engineering teams responsible for lead conversion and customer onboarding flows.

## Scope

In scope:

- Retrieve one lead by `phone`.
- Normalize accepted phone number input through the existing phone formatter.
- Return the lead's basic attributes.
- Return selected package codes attached to the lead.
- Return the lead's home center summary.
- Return linked customer profile summary when available.
- Return a standard project response envelope.

Out of scope:

- Creating, updating, inviting, joining, or converting a lead.
- Listing multiple leads.
- Searching by email, lead ID, customer profile ID, or home center.
- Returning program, service, appointment, notification, or associate assignment data.
- Mutating `seen`, audit, or access-tracking fields.

## Endpoint Contract

### Request

```http
GET /external/customer-leads/?phone=<phone>
```

Authentication: Not required in the current implementation.

Query parameters:

| Name | Required | Type | Description |
|---|---:|---|---|
| `phone` | Yes | string | Customer phone number used to find a lead through the linked customer user phone. URL-encode `+` as `%2B`. |

Example:

```http
GET /external/customer-leads/?phone=%2B91-9999911118
```

### Success Response

HTTP status: `200 OK`

Response envelope:

```json
{
  "detail": "Details.",
  "data": {}
}
```

Example:

```json
{
  "detail": "Details.",
  "data": {
    "id": "019f405d-1064-7392-9cee-c4e46288c630",
    "unique_id": "L-0009",
    "first_name": "John",
    "last_name": "Doe",
    "gender": "Male",
    "date_of_birth": "1986-01-01",
    "phone": "+91-9999911118",
    "email": null,
    "description": null,
    "is_active": true,
    "is_client": true,
    "is_invited": false,
    "is_joined": true,
    "converted_on": "2026-07-08T11:48:05.264688+05:30",
    "packages": [
      "P001"
    ],
    "home_center": {
      "id": "019ed45d-d6c4-7534-830e-501019fd98dd",
      "code": "CT-0051",
      "name": "Biopeak Mumbai"
    },
    "home_center_id": "019ed45d-d6c4-7534-830e-501019fd98dd",
    "customer_profile": {
      "id": "019f4060-5e43-70f6-9f8e-7221fb9a9333",
      "contact_email": null,
      "phone": "+91-9999911118",
      "first_name": "John",
      "last_name": "Doe",
      "gender": "Male",
      "date_of_birth": null,
      "image": null,
      "is_main": true,
      "is_legacy": false,
      "is_onboarding_complete": false,
      "created_at": "2026-07-08T11:48:05.251276+05:30",
      "updated_at": "2026-07-08T11:48:05.251282+05:30"
    },
    "created_at": "2026-07-08T11:44:28.709061+05:30",
    "updated_at": "2026-07-08T11:48:05.264791+05:30"
  }
}
```

### Error Responses

Lead not found:

HTTP status: `404 Not Found`

```json
{
  "detail": "Lead not found"
}
```

Invalid or missing phone:

- Current behavior depends on `PhoneNumberFormat.clean(raise_exception=False)` and the queryset result.
- The route currently falls through to `404 Not Found` when no lead matches the cleaned phone value.

## Response Fields

| Field | Type | Nullable | Description |
|---|---|---:|---|
| `id` | UUID string | No | Lead primary key. |
| `unique_id` | string | No | Human-readable lead identifier, for example `L-0009`. |
| `first_name` | string | No | Lead first name. |
| `last_name` | string | No | Lead last name. |
| `gender` | string | Yes | Display label for gender. |
| `date_of_birth` | date string | Yes | Lead date of birth in `YYYY-MM-DD` format. |
| `phone` | string | No | Lead phone number. |
| `email` | string | Yes | Lead email address. |
| `description` | string | Yes | Optional lead notes or description. |
| `is_active` | boolean | No | Whether the lead is active. |
| `is_client` | boolean | No | Whether the lead has been marked as a client. |
| `is_invited` | boolean | No | Whether an invitation has been sent or recorded. |
| `is_joined` | boolean | No | Whether the customer has joined. |
| `converted_on` | datetime string | Yes | Lead conversion timestamp. |
| `packages` | array of strings | Yes | Package codes selected for the lead. Current codes include `P001` through `P006`. |
| `home_center` | object | Yes | Summary of the lead's home center. |
| `home_center.id` | UUID string | No | Center primary key. |
| `home_center.code` | string | No | Center code. |
| `home_center.name` | string | No | Center name. |
| `home_center_id` | UUID string | Yes | Home center primary key. |
| `customer_profile` | object | Yes | Linked customer profile summary. |
| `created_at` | datetime string | No | Lead creation timestamp. |
| `updated_at` | datetime string | No | Lead last update timestamp. |

Customer profile fields:

| Field | Type | Nullable | Description |
|---|---|---:|---|
| `id` | UUID string | No | Customer profile primary key. |
| `contact_email` | string | Yes | Customer contact email. |
| `phone` | string | No | Customer user phone. |
| `first_name` | string | No | Customer profile first name. |
| `last_name` | string | No | Customer profile last name. |
| `gender` | string | Yes | Customer profile gender display label. |
| `date_of_birth` | date string | Yes | Customer profile date of birth. |
| `image` | string | Yes | Customer profile image URL or path. |
| `is_main` | boolean | No | Whether this is the main customer profile. |
| `is_legacy` | boolean | No | Whether this profile is legacy data. |
| `is_onboarding_complete` | boolean | No | Whether onboarding is complete. |
| `created_at` | datetime string | No | Customer profile creation timestamp. |
| `updated_at` | datetime string | No | Customer profile last update timestamp. |

Package code reference:

| Code | Label |
|---|---|
| `P001` | Essential Health Program |
| `P002` | Essential Health with Digital Twin |
| `P003` | Edge Program |
| `P004` | Edge Plus Program |
| `P005` | Elite Longevity Programme |
| `P006` | Customised Program |

## Functional Requirements

1. The API must accept a `GET` request at `/external/customer-leads/`.
2. The API must require a `phone` query parameter for lookup.
3. The API must normalize the supplied phone number using the existing project phone formatting utility.
4. The API must find a lead through `Lead.customer_profile.customer.user.phone`.
5. The API must return exactly one lead record.
6. The API must return `404 Not Found` with `Lead not found` when no matching lead exists.
7. The API must return read-only lead data; no write operation is allowed.
8. The API must include nested `home_center` data when a home center exists.
9. The API must include nested `customer_profile` data when the lead is linked to a customer profile.
10. The API must use the standard response envelope with `detail` and `data`.

## Non-Functional Requirements

Performance:

- The lead lookup should complete with a small, bounded number of queries.
- The view should use relation loading for nested customer profile and user data.

Security and privacy:

- The endpoint exposes personally identifiable information by phone number.
- Authentication, authorization, rate limiting, and caller identification are not defined in the current route.
- Phone enumeration risk must be reviewed before exposing this route outside trusted infrastructure.

Reliability:

- The response shape must remain stable for external consumers.
- Nullable fields must remain present in the response with `null` values instead of being omitted.

Compatibility:

- Dates must be serialized as ISO date strings.
- Datetimes must be serialized as timezone-aware ISO 8601 strings.
- Phone numbers in examples should be URL-encoded when included in a query string.

## Data Source and Lookup Logic

The current route does not look up `Lead.phone` directly. It filters leads by:

```text
Lead.customer_profile.customer.user.phone == cleaned phone query parameter
```

Implication:

- A lead that has the requested `phone` value but is not linked to a customer profile will not be returned by this endpoint.
- A lead linked to a customer profile whose user phone differs from `Lead.phone` will be found by the customer user phone, not by `Lead.phone`.

## Acceptance Criteria

1. Given a valid phone number linked to a converted lead's customer profile, when the caller sends `GET /external/customer-leads/?phone=<phone>`, then the API returns `200 OK` with the lead payload.
2. Given an unknown phone number, when the caller sends the request, then the API returns `404 Not Found` with `detail` equal to `Lead not found`.
3. Given a matching lead with a home center, then `home_center` includes `id`, `code`, and `name`.
4. Given a matching lead with a customer profile, then `customer_profile` includes identity, contact, onboarding, and timestamp fields.
5. Given nullable fields such as `email`, `description`, or `converted_on`, then the response includes those keys with `null` when values are absent.
6. Given package code `P001`, then the response preserves the package code value rather than replacing it with a label.

## Analytics and Observability

Recommended events and metrics:

- Request count by caller, if caller identity is added.
- Lookup success count.
- Lookup not-found count.
- Invalid phone count, if explicit phone validation is added.
- Latency percentiles.
- Rate-limit rejection count, if rate limiting is added.

## Dependencies

- `Lead` model and its `customer_profile` relation.
- `CustomerProfile`, `Customer`, and `User` phone data.
- `MinimumCenterSerializer`.
- `BaseCustomerProfileSerializer`.
- `PhoneNumberFormat`.
- Standard project response and exception handlers.

## Open Questions

The implementation does not define the following product decisions:

1. Should this endpoint remain unauthenticated, or should it require an API key, signed request, JWT, or allowlisted caller?
2. Should lookup use `Lead.phone`, `Customer.user.phone`, or both?
3. Should unconverted leads without `customer_profile` be discoverable by this route?
4. Should missing or invalid `phone` return `400 Bad Request` instead of `404 Not Found`?
5. Should inactive leads be returned, or should `is_active=False` leads be hidden?
6. Should package labels be returned alongside package codes?
7. Should the endpoint return multiple records if historical lead duplication is ever allowed, or must lead phone uniqueness remain guaranteed?
8. Should sensitive fields such as email, date of birth, and profile image be omitted for external callers?
9. Should the route be rate limited to reduce phone enumeration risk?

## Release Notes

This PRD documents the current API behavior as of 2026-07-08. Any behavior changes from the open questions should be captured in this document before implementation.
