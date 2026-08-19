# Customer Profile Documents List — Frontend ePRD

## 1. Purpose

Build a paginated document list for one customer profile. The collection
combines documents from results attached to all programs owned by the selected
profile, regardless of program type.

This is a read-only list request. It does not create results, upload files, or
change document state.

## 2. Endpoint and Access

```http
GET /profiles/:customer_profile_id/documents/
Authorization: Bearer <access_token>
```

Administrators, associates, and customers can access the endpoint.

- Administrators and associates can request any existing customer-profile UUID.
- A customer can request only a profile belonging to their own customer
  account. A profile owned by another customer is returned as not found.
- `X-Center-ID` is not required and does not scope this endpoint.

There is no request body, payload, or `Content-Type` requirement.

The path parameter is the `CustomerProfile` UUID. Do not send a Program,
CompositeProgram, ProgramService, result, or document UUID in its place.

## 3. Query Parameters

| Parameter | Required | Values | Behavior |
|---|---|---|---|
| `search` | No | String | Case-insensitive match against filename, provider name, product name, or assigned service name |
| `active` | No | `0`, `1` | Filters the document's active state; omission returns both states |
| `document_type` | No | Document-type code | Exact match against the parent result's document type |
| `document_category` | No | `report`, `raw` | Exact document-category match |
| `date_from` | No | `YYYY-MM-DD` | Inclusive lower bound on the parent result's sample-collection date |
| `date_to` | No | `YYYY-MM-DD` | Inclusive upper bound on the parent result's sample-collection date |
| `page` | No | Positive integer | Requested page; defaults to the first page |
| `limit` | No | Positive integer up to `50` | Requested page size; defaults to the global page size |

`date_from` and `date_to` filter `sample_collection_date`, not document upload
time or report-generation date. A result whose sample-collection date is null
is excluded whenever either boundary is supplied. Both boundaries are
inclusive, and `date_to` must be on or after `date_from`.

Example:

```http
GET /profiles/:customer_profile_id/documents/?search=blood&active=1&document_type=blood&document_category=report&date_from=2026-08-01&date_to=2026-08-17&page=1&limit=10
Authorization: Bearer <access_token>
```

All filters can be used independently or combined. Results are ordered by
document creation time, newest first.

## 4. Filter Codes

### Active state

| UI value | Query value |
|---|---|
| All | Omit `active` |
| Active | `active=1` |
| Inactive | `active=0` |

### Document category

| Display value | Code |
|---|---|
| Report file | `report` |
| Raw data file | `raw` |

### Result mode

Result mode is returned for display but is not a filter on this endpoint.

| Display value | Code |
|---|---|
| Upload | `upload` |
| Fetch | `fetch` |

### Document type

Submit a backend document-type code such as `blood`, `oligoscan`,
`dxa_core_scan`, or `other`. Render the returned `document_type` label and use
`document_type_code` for comparisons and query state. The complete allowed
code set is the shared `ServiceDocumentType` contract documented by the
product allowed-document workflow.

## 5. Success Response

```json
{
  "detail": "All data.",
  "count": 1,
  "next": null,
  "previous": null,
  "data": [
    {
      "id": "<document_uuid>",
      "result": {
        "id": "<result_uuid>",
        "program_service": {
          "id": "<program_service_uuid>",
          "service": {
            "id": "<service_uuid>",
            "name": "Blood Diagnostics",
            "service_category": "Assessment",
            "service_category_code": "assessment",
            "image": "<url|null>"
          },
          "composite_program": {
            "id": "<composite_program_uuid>",
            "uid": "P0001",
            "name": "Longevity Program"
          },
          "composite_template": {
            "id": "<composite_template_uuid>",
            "code": "<template_sku>",
            "name": "Longevity Template",
            "is_active": true
          }
        },
        "product": {
          "id": "<product_uuid>",
          "name": "Blood Panel",
          "code": "<product_code>"
        },
        "provider_name": "Provider name",
        "product_name": "Blood Panel",
        "result_mode": "Upload",
        "result_mode_code": "upload",
        "document_type": "Blood diagnostics Report",
        "document_type_code": "blood",
        "documents_count": 1,
        "sample_collection_date": "2026-08-10",
        "report_generation_date": "2026-08-12"
      },
      "file": "<file_url>",
      "filename": "blood-report.pdf",
      "content_type": "application/pdf",
      "document_category": "Report file",
      "document_category_code": "report",
      "is_active": true,
      "created_at": "<ISO-8601_datetime>",
      "updated_at": "<ISO-8601_datetime>"
    }
  ]
}
```

`result.product`, `provider_name`, and `product_name` can be null. Render
display fields and retain the corresponding `*_code` fields for filters and
comparisons.

`result.program_service.composite_program` and `composite_template` are direct,
nullable references. Both are populated when the source ProgramService belongs
to a composite program and are `null` for other program types.

## 6. Frontend Types

```ts
type ActiveFilter = "0" | "1";
type ServiceCategoryCode = "assessment" | "therapy" | "consultation";
type ServiceDocumentCategoryCode = "report" | "raw";
type ServiceResultModeCode = "upload" | "fetch";
type ServiceDocumentTypeCode =
  | "other"
  | "blood"
  | "oligoscan"
  | "somfit"
  | "metsights_pp"
  | "evo_360"
  | "omics_urine"
  | "omics_cortisol"
  | "dxa_core_scan"
  | "dxa_body_composition"
  | "dxa_segmental_analysis"
  | "breathing_stress_profile_report"
  | "breathing_stress_respiratory_report"
  | "breathing_stress_communication_style"
  | "breathing_stress_cognifit"
  | "usg_carotid_doppler"
  | "usg_neck"
  | "usg_abdomen_pelvis"
  | "usg_arterial_doppler"
  | "usg_venous_doppler"
  | "usg_sonomammogram"
  | "usg_scrotum"
  | "usg_follicular_tvs"
  | "usg_pelvic_tvs"
  | "usg_others"
  | "genetics_functional"
  | "genetics_nutri_dna"
  | "genetics_health_insights"
  | "genetics_breast_ovarian_cancer"
  | "genetics_comprehensive"
  | "genetics_pharmacogenomics"
  | "genetics_inherited_cancer"
  | "genetics_nutri_dna_pdf"
  | "genetics_nutri_dna_vcf"
  | "bugspeaks_report"
  | "steroid_hormone_profile"
  | "steroid_hormone_nad_longevity"
  | "steroid_hormone_nutri_toxic"
  | "steroid_hormone_fatty_acid"
  | "steroid_hormone_neurotransmitter_profile"
  | "fitness_strength_pelvic_floor"
  | "fitness_strength_physical_assessment"
  | "fitness_strength_vo2_max";

interface CustomerProfileDocumentFilters {
  search?: string;
  active?: ActiveFilter;
  document_type?: ServiceDocumentTypeCode;
  document_category?: ServiceDocumentCategoryCode;
  date_from?: string;
  date_to?: string;
  page: number;
  limit: number;
}

interface CustomerProfileDocument {
  id: string;
  result: {
    id: string;
    program_service: {
      id: string;
      service: {
        id: string;
        name: string;
        service_category: string;
        service_category_code: ServiceCategoryCode;
        image: string | null;
      };
      composite_program: {
        id: string;
        uid: string | null;
        name: string | null;
      } | null;
      composite_template: {
        id: string;
        name: string;
        description: string | null;
        is_active: boolean;
      } | null;
    };
    product: { id: string; name: string; code: string } | null;
    provider_name: string | null;
    product_name: string | null;
    result_mode: string;
    result_mode_code: ServiceResultModeCode;
    document_type: string;
    document_type_code: ServiceDocumentTypeCode;
    documents_count: number;
    sample_collection_date: string | null;
    report_generation_date: string | null;
  };
  file: string;
  filename: string;
  content_type: string;
  document_category: string;
  document_category_code: ServiceDocumentCategoryCode;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface CustomerProfileDocumentListResponse {
  detail: string;
  count: number;
  next: string | null;
  previous: string | null;
  data: CustomerProfileDocument[];
}
```

## 7. List UI

Show one row per document, keyed by document `id`. Recommended columns are:

1. Filename.
2. Assigned service name.
3. Provider and product.
4. Document type.
5. Document category.
6. Sample-collection date, with an em dash for null.
7. Active/inactive badge.
8. File action.

Open or download the returned `file` URL; do not construct a media URL from
the filename. Search should be debounced. Changing search, any filter, or page
size resets `page` to `1`.

## 8. Cache, Empty, and Error States

The query-cache key must include customer-profile ID, search, active state,
document type, document category, both dates, page, and limit. Do not merge
pages belonging to different profiles or filter states.

**Clear filters** removes search and every filter, returns to page `1`, and
retains the customer-profile ID and selected page size.

- Initial load: show the standard list skeleton.
- Empty profile: explain that the profile has no documents across its programs.
- Empty filtered result: offer **Clear filters**.
- `400`: show the returned date-filter validation message. A reversed date
  range returns `Date to must be on or after date from.`
- `401`: follow the authentication-expiry flow.
- `403`: show the standard unauthorized state.
- `404`: show that the profile was not found or is not owned by the signed-in
  customer.
- `500`: retain filters and offer retry.

## 9. Acceptance Criteria

- The frontend calls `/profiles/:customer_profile_id/documents/` with a
  `CustomerProfile` UUID.
- The request is a plain `GET` with no body, payload, multipart data, or
  `Content-Type` header.
- Administrators and associates can list an existing profile without
  `X-Center-ID`.
- Customers can list their own profiles and cannot list another customer's
  profile.
- The response can contain documents from multiple programs and program types.
- Composite-program rows expose direct composite-program and template
  references; both fields are null for non-composite programs.
- Search covers filename, provider, product, and service metadata.
- Active, document-type, and category filters submit codes, not labels.
- Date filtering is inclusive and operates only on sample-collection date.
- Pagination uses `page` and `limit`, with `limit` no greater than `50`.
- Rows use document UUIDs as keys and nested ProgramService UUIDs for
  source-service navigation.
- Loading, empty, validation, forbidden, missing-profile, and retryable-error
  states are implemented.
