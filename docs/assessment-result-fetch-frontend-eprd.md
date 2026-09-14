# Assessment Result Fetch ePRD

Enable an admin or associate to submit provider-backed assessment result requests
and read the collected results through the existing program-service APIs.

All endpoints require:

```http
Authorization: Bearer <token>
```

## Logical Flow

1. **List providers** — Load active providers assigned to the assessment service.
2. **List products** — Load active products for the selected provider and service.
3. **Submit result request** — Send the provider-configured data and start the asynchronous fetch.
4. **List result requests** — Load request history when the screen opens or the user explicitly refreshes it.
5. **Read result request** — Load one request only when the user opens its details.
6. **List assessment results** — Load collected manual and fetched results through the normal results-screen lifecycle.
7. **Refetch result request** — Delete the request's existing results and start the same request again.
8. **Cancel result request** — Change an eligible request's persisted status to cancelled.

The backend is the authority for service, provider, product, and request state.
The frontend must not prevalidate backend lifecycle invariants. Do not poll result
requests or results after create, refetch, or cancel.

`partially_fetched` means the provider fetch has finished with at least one PDF,
VCF, or structured JSON artifact available, but one or more expected artifacts
could not be collected. Display the available results and `failure_detail`.
Partially fetched requests may be cancelled or explicitly refetched.

## API Requests

### 1. List providers

Returns active providers that have an active product assignment for the
assessment service.

**Method:** `GET`

**URL:** `<baseURL>/programs/program-services/assessment-services/:assessment_service_id/providers/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `assessment_service_id` | Yes | `5af40854-ccde-7f06-96a3-d6aa35b07055` | ProgramService UUID for an assessment |

#### Query Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `page` | No | `1` | Defaults to the first page |
| `limit` | No | `10` | Maximum 50 |

#### Response — `200 OK`

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
      "name": "BugSpeaks",
      "code": "PV-0007",
      "is_api_enabled": true,
      "fetch_fields": [
        "bugspeaks_id"
      ],
      "fetch_profile_fields": []
    }
  ]
}
```

Use `name` as the display value and `id` as `provider_id`. The two field
arrays define the exact keys that must later be submitted under `data` and
`profile_data`. A listed provider may have `is_api_enabled: false`; the
create endpoint remains authoritative and will reject it.

For every key returned in `fetch_profile_fields`, prefill `profile_data` from
the current customer when a corresponding value is available:

| Profile field | Prefill value |
| --- | --- |
| `full_name` | Trimmed first and last name joined with one space |
| `age` | Completed calendar years calculated from the date of birth |
| `gender` | Current gender value displayed for the customer profile |
| `date_of_birth` | Date of birth in ISO `YYYY-MM-DD` format |
| `email` | Customer contact email |
| `phone` | Customer account phone |

Prefill only requested keys and keep every prefilled value editable. Leave a
requested value empty when the customer record does not provide it; staff must
complete all empty values before submitting because the backend rejects empty
profile fields. The submitting user is responsible for confirming that the
profile data is accurate. The backend does not match these submitted values to
the provider-returned identity.

### 2. List products

Returns active products assigned to the assessment service. Send the selected
provider's `code` to narrow the list.

**Method:** `GET`

**URL:** `<baseURL>/programs/program-services/assessment-services/:assessment_service_id/products/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `assessment_service_id` | Yes | `5af40854-ccde-7f06-96a3-d6aa35b07055` | ProgramService UUID for an assessment |

#### Query Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `provider` | No | `PV-0007` | Exact provider code |
| `page` | No | `1` | Defaults to the first page |
| `limit` | No | `10` | Maximum 50 |

#### Response — `200 OK`

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
      "name": "Gut Microbiome",
      "code": "PD-0018"
    }
  ]
}
```

Use `name` as the display value and `id` as `product_id`. Clear the selected
product and dynamic field values whenever the provider changes.

### 3. Submit result request

Creates a queued result request and starts its provider handler.

**Method:** `POST`

**URL:** `<baseURL>/programs/program-services/assessment-services/:assessment_service_id/result-requests/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `assessment_service_id` | Yes | `5af40854-ccde-7f06-96a3-d6aa35b07055` | ProgramService UUID for an assessment |

#### Payload

```json
{
  "provider_id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
  "product_id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
  "data": {
    "bugspeaks_id": "BPK-2026-0148"
  },
  "profile_data": {}
}
```

Both `data` and `profile_data` are required. Their keys must exactly match
the selected provider's corresponding field arrays. Missing keys, unexpected
keys, `null`, empty strings, whitespace-only strings, empty arrays, and empty
objects are rejected. Boolean `false` and numeric `0` are valid values. An
empty configured array must be submitted as `{}`.

The backend validates the assessment service, provider, product, active
service-product assignment, provider API configuration, and registered provider
handler.

#### Response — `201 Created`

```json
{
  "detail": "Create success.",
  "data": {
    "id": "5af40da2-b2bb-758f-a096-6707400990bb",
    "provider": {
      "id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
      "name": "BugSpeaks",
      "code": "PV-0007"
    },
    "product": {
      "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
      "name": "Gut Microbiome",
      "code": "PD-0018"
    },
    "data": {
      "bugspeaks_id": "BPK-2026-0148"
    },
    "status": "Queued",
    "status_code": "queued",
    "attempts_count": 0,
    "failure_detail": "",
    "started_at": null,
    "completed_at": null,
    "results": [],
    "created_by": {
      "id": "5af4003b-9f56-7580-8c19-abf2ce7c820f",
      "email": "admin@example.com",
      "first_name": "Aarav",
      "last_name": "Sharma",
      "image": null,
      "last_login": "2026-09-08T09:30:00+05:30"
    },
    "created_at": "2026-09-08T10:00:00+05:30",
    "updated_at": "2026-09-08T10:00:00+05:30"
  }
}
```

`profile_data` is write-only and is never returned. Treat the response as
acceptance of the request; do not start a polling loop.

#### Errors

Unavailable provider or product:

```json
{
  "detail": {
    "product_id": [
      "This product is not available for result fetching."
    ]
  }
}
```

Unsupported provider registry:

```json
{
  "detail": {
    "product_id": [
      "Result fetching is not supported for this product."
    ]
  }
}
```

### 4. List result requests

Returns the assessment service's request history in newest-first order. This
read remains available when the program service is inactive.

**Method:** `GET`

**URL:** `<baseURL>/programs/program-services/assessment-services/:assessment_service_id/result-requests/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `assessment_service_id` | Yes | `5af40854-ccde-7f06-96a3-d6aa35b07055` | ProgramService UUID for an assessment |

#### Query Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `status` | No | `completed` | One of `queued`, `running`, `completed`, `partially_fetched`, `failed`, or `cancelled`; invalid values leave the list unfiltered |
| `page` | No | `1` | Defaults to the first page |
| `limit` | No | `10` | Maximum 50 |

#### Response — `200 OK`

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "5af40da2-b2bb-758f-a096-6707400990bb",
      "provider": {
        "id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
        "name": "BugSpeaks",
        "code": "PV-0007"
      },
      "product": {
        "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
        "name": "Gut Microbiome",
        "code": "PD-0018"
      },
      "data": {
        "bugspeaks_id": "BPK-2026-0148"
      },
      "status": "Completed",
      "status_code": "completed",
      "attempts_count": 1,
      "failure_detail": "",
      "started_at": "2026-09-08T10:00:01+05:30",
      "completed_at": "2026-09-08T10:00:05+05:30",
      "results": [
        {
          "id": "5af41000-81af-72c7-9c8f-845e2982288e",
          "provider_name": "BugSpeaks",
          "product_name": "Gut Microbiome",
          "result_mode": "Fetch",
          "result_mode_code": "fetch",
          "document_type": "Bugspeaks Report",
          "document_type_code": "bugspeaks_report",
          "sample_collection_date": "2026-09-01",
          "report_generation_date": "2026-09-08"
        }
      ],
      "created_by": {
        "id": "5af4003b-9f56-7580-8c19-abf2ce7c820f",
        "email": "admin@example.com",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "image": null,
        "last_login": "2026-09-08T09:30:00+05:30"
      },
      "created_at": "2026-09-08T10:00:00+05:30",
      "updated_at": "2026-09-08T10:00:05+05:30"
    }
  ]
}
```

Load this endpoint only through normal screen loading or explicit user refresh.

### 5. Read result request

Returns one assessment result request on demand.

**Method:** `GET`

**URL:** `<baseURL>/programs/program-services/result-requests/:result_request_id/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `result_request_id` | Yes | `5af40da2-b2bb-758f-a096-6707400990bb` | ResultRequest UUID |

#### Response — `200 OK`

```json
{
  "detail": "Details.",
  "data": {
    "id": "5af40da2-b2bb-758f-a096-6707400990bb",
    "provider": {
      "id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
      "name": "BugSpeaks",
      "code": "PV-0007"
    },
    "product": {
      "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
      "name": "Gut Microbiome",
      "code": "PD-0018"
    },
    "data": {
      "bugspeaks_id": "BPK-2026-0148"
    },
    "status": "Failed",
    "status_code": "failed",
    "attempts_count": 1,
    "failure_detail": "Failed to fetch files for bugspeaks report",
    "started_at": "2026-09-08T10:00:01+05:30",
    "completed_at": "2026-09-08T10:00:05+05:30",
    "results": [],
    "created_by": {
      "id": "5af4003b-9f56-7580-8c19-abf2ce7c820f",
      "email": "admin@example.com",
      "first_name": "Aarav",
      "last_name": "Sharma",
      "image": null,
      "last_login": "2026-09-08T09:30:00+05:30"
    },
    "created_at": "2026-09-08T10:00:00+05:30",
    "updated_at": "2026-09-08T10:00:05+05:30"
  }
}
```

Display `failure_detail` when the explicitly loaded request is failed or partially
fetched. A partially fetched response uses `"status": "Partially Fetched"` and
`"status_code": "partially_fetched"` and can contain available results. Do not
call this endpoint on an interval or retry timer.

#### Error — `404 Not Found`

```json
{
  "detail": "Result request not found."
}
```

### 6. List assessment results

Returns manual and provider-fetched results for the assessment service in
newest-first order.

**Method:** `GET`

**URL:** `<baseURL>/programs/program-services/assessment-services/:assessment_service_id/results/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `assessment_service_id` | Yes | `5af40854-ccde-7f06-96a3-d6aa35b07055` | ProgramService UUID for an assessment |

#### Query Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `product` | No | `5af40b13-2e95-75d5-870b-e1b65b462e29` | Exact product UUID |
| `page` | No | `1` | Defaults to the first page |
| `limit` | No | `10` | Maximum 50 |

#### Response — `200 OK`

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "5af41000-81af-72c7-9c8f-845e2982288e",
      "product": {
        "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
        "name": "Gut Microbiome",
        "code": "PD-0018"
      },
      "provider_name": "BugSpeaks",
      "product_name": "Gut Microbiome",
      "result_mode": "Fetch",
      "result_mode_code": "fetch",
      "document_type": "Bugspeaks Report",
      "document_type_code": "bugspeaks_report",
      "sample_collection_date": "2026-09-01",
      "report_generation_date": "2026-09-08",
      "documents_count": 2,
      "documents": [
        {
          "id": "5af4111b-f8dc-74bf-8cc9-f1f5b0181783",
          "file": "<document_url>",
          "filename": "BugSpeaks_PDF_Report_BPK-2026-0148.pdf",
          "content_type": "application/pdf",
          "document_category": "Report file",
          "document_category_code": "report",
          "module_category": "Functional & Metabolic Tests",
          "module_category_code": "functional_metabolic_tests"
        }
      ],
      "created_by": {
        "id": "5af4003b-9f56-7580-8c19-abf2ce7c820f",
        "email": "admin@example.com",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "image": null,
        "last_login": "2026-09-08T09:30:00+05:30"
      },
      "is_active": true,
      "created_at": "2026-09-08T10:00:05+05:30",
      "updated_at": "2026-09-08T10:00:05+05:30"
    }
  ]
}
```

Fetched results have `result_mode_code: "fetch"`. The nested `documents`
preview contains at most three files. Load this endpoint only when the results
screen normally loads, its query changes, or the user explicitly refreshes it.

### 7. Refetch result request

Deletes the request's existing result rows and starts the same request again
with its original `data` and `profile_data`.

**Method:** `POST`

**URL:** `<baseURL>/programs/program-services/result-requests/:result_request_id/refetch/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `result_request_id` | Yes | `5af40da2-b2bb-758f-a096-6707400990bb` | ResultRequest UUID |

#### Payload

```json
{}
```

#### Response — `201 Created`

```json
{
  "detail": "Create success.",
  "data": {
    "id": "5af40da2-b2bb-758f-a096-6707400990bb",
    "provider": {
      "id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
      "name": "BugSpeaks",
      "code": "PV-0007"
    },
    "product": {
      "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
      "name": "Gut Microbiome",
      "code": "PD-0018"
    },
    "data": {
      "bugspeaks_id": "BPK-2026-0148"
    },
    "status": "Queued",
    "status_code": "queued",
    "attempts_count": 1,
    "failure_detail": "",
    "started_at": null,
    "completed_at": null,
    "results": [],
    "created_at": "2026-09-08T10:00:00+05:30",
    "updated_at": "2026-09-08T10:15:00+05:30"
  }
}
```

Refetch deletes all linked `ServiceResult` rows and cascades deletion to their
document database rows. It then clears failure and timing state, recomputes
result/document counters, and queues the same request. Deleted rows are not
restored if the new fetch fails.

A queued or running request updated within the previous second is rejected.
Refetch also requires the program service, provider, provider API configuration,
product, and resolved handler to remain active and available. Do not poll after
a successful response.

#### Errors

Recent queued or running request:

```json
{
  "detail": "A result fetch is already queued or running."
}
```

Unavailable refetch dependencies:

```json
{
  "detail": "This result request is not currently available for refetching."
}
```

### 8. Cancel result request

Changes only the request's persisted status and update timestamp.

**Method:** `POST`

**URL:** `<baseURL>/programs/program-services/result-requests/:result_request_id/cancel/`

#### Path Parameters

| Name | Required | Example | Notes |
| --- | --- | --- | --- |
| `result_request_id` | Yes | `5af40da2-b2bb-758f-a096-6707400990bb` | ResultRequest UUID |

#### Payload

```json
{}
```

#### Response — `201 Created`

```json
{
  "detail": "Create success.",
  "data": {
    "id": "5af40da2-b2bb-758f-a096-6707400990bb",
    "provider": {
      "id": "5af40a28-d83b-7900-b5dc-11cc2689f585",
      "name": "BugSpeaks",
      "code": "PV-0007"
    },
    "product": {
      "id": "5af40b13-2e95-75d5-870b-e1b65b462e29",
      "name": "Gut Microbiome",
      "code": "PD-0018"
    },
    "data": {
      "bugspeaks_id": "BPK-2026-0148"
    },
    "status": "Cancelled",
    "status_code": "cancelled",
    "attempts_count": 1,
    "failure_detail": "Failed to fetch files for bugspeaks report",
    "started_at": "2026-09-08T10:00:01+05:30",
    "completed_at": "2026-09-08T10:00:05+05:30",
    "results": [],
    "created_at": "2026-09-08T10:00:00+05:30",
    "updated_at": "2026-09-08T10:20:00+05:30"
  }
}
```

Queued, running, failed, and partially fetched requests may be cancelled.
Completed requests and requests already marked cancelled are rejected. Existing
results, documents, failure details, attempt counts, and timestamps are
preserved. Do not poll after a successful response.

#### Errors

Already cancelled:

```json
{
  "detail": "Result request is already cancelled."
}
```

Completed request:

```json
{
  "detail": "A completed result request cannot be cancelled."
}
```
