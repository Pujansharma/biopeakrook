# Assessment Program-Service Result Upload — Frontend ePRD

## 1. Purpose

Build the complete frontend workflow for viewing an assigned assessment service,
creating one result with its shared metadata, uploading files into that result,
and listing the completed results.

The result owns the selected product and document type. Every uploaded document
inherits that metadata and owns only its file and category.

## 2. API Map

| Method | Purpose | Endpoint |
|---|---|---|
| `GET` | Retrieve ProgramService detail | `/programs/program-services/assessment-services/:program_service_id/` |
| `GET` | List supported providers | `/programs/program-services/assessment-services/:program_service_id/providers/` |
| `GET` | List supported products | `/programs/program-services/assessment-services/:program_service_id/products/` |
| `GET` | List product-specific document types | `/products/:product_id/allowed-documents/` |
| `POST` | Create result metadata | `/programs/program-services/assessment-services/:program_service_id/results/` |
| `POST` | Upload one file into a result | `/programs/program-services/results/:result_id/documents/` |
| `GET` | List results in the ProgramService | `/programs/program-services/assessment-services/:program_service_id/results/` |
| `DELETE` | Delete one uploaded document | `/programs/program-result-documents/:document_id/` |

`program_service_id`, `product_id`, `result_id`, and `document_id` are different
UUIDs and are not interchangeable.

## 3. Access

All requests require:

```http
Authorization: Bearer <access_token>
```

Administrators and associates can use the workflow. Customers cannot.
`X-Center-ID` is not required.

Provider and product selection is available only while the ProgramService is
active. Detail and historical result/document lists remain readable after the
ProgramService becomes inactive.

## 4. Required Frontend Flow

1. Retrieve and display the assessment ProgramService detail.
2. Retrieve the providers supported by its assigned catalogue service.
3. After provider selection, retrieve products with the provider code filter.
4. After product selection, retrieve the product's allowed document types.
5. Create one result using the product UUID, selected document-type value, and
   optional dates.
6. Read the created result UUID from `data.id`.
7. Upload files one at a time into that result. Each file supplies its own
   `document_category`.
8. Mark the client workflow complete only after all intended file requests
   succeed or the user explicitly accepts any failed items.
9. Refetch the ProgramService result list and detail.

There is no finalize endpoint and no upload-complete status mutation.

## 5. ProgramService Detail

```http
GET /programs/program-services/assessment-services/:program_service_id/
Authorization: Bearer <access_token>
```

Use `data.is_active` to enable or disable creation controls. The nested
`data.service.id` is the catalogue Service UUID; it must not replace the
ProgramService UUID in subsequent URLs.

## 6. Provider Selection

```http
GET /programs/program-services/assessment-services/:program_service_id/providers/
Authorization: Bearer <access_token>
```

The response is paginated and contains distinct active providers that have at
least one active product connected through an active service-product assignment.

Provider item:

```json
{
  "id": "<provider_uuid>",
  "name": "Provider name",
  "code": "PV-0001"
}
```

An unknown, non-assessment, or inactive ProgramService returns `404`.

## 7. Product Selection

```http
GET /programs/program-services/assessment-services/:program_service_id/products/?provider=PV-0001
Authorization: Bearer <access_token>
```

`provider` is an optional exact provider-code filter. Send the `code` returned
by the provider endpoint, not the provider UUID or name. An unknown code returns
an empty paginated collection.

Product item:

```json
{
  "id": "<product_uuid>",
  "name": "Product name",
  "code": "PC-0001"
}
```

Only active products with an active provider and active assignment are returned.

When the provider changes, clear both the selected product and document type
before loading the new product page.

## 8. Allowed Document Types

```http
GET /products/:product_id/allowed-documents/
Authorization: Bearer <access_token>
```

The response is not paginated:

```json
{
  "detail": "Allowed document types retrieved.",
  "data": [
    {
      "display_name": "Blood diagnostics Report",
      "value": "blood"
    },
    {
      "display_name": "Other",
      "value": "other"
    }
  ]
}
```

Render `display_name` and submit `value`. `Other` is always allowed. Do not
hardcode the mapping or derive values from labels.

When the product changes, clear the previous type and load the new metadata.

## 9. Create Result Metadata

```http
POST /programs/program-services/assessment-services/:program_service_id/results/
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "product_id": "<product_uuid>",
  "document_type": "blood",
  "sample_collection_date": "2026-08-01",
  "report_generation_date": "2026-08-10"
}
```

Rules:

- `product_id` is required and cannot be `null`;
- `document_type` is required and must be allowed for the selected product;
- both dates are optional and nullable;
- no ordering rule is applied between the dates;
- `result_mode` is server-controlled and is `upload`;
- provider and product names are snapshotted by the backend.

Relevant success data:

```json
{
  "id": "<result_uuid>",
  "product": {
    "id": "<product_uuid>",
    "name": "Product name",
    "code": "PC-0001"
  },
  "provider_name": "Provider name",
  "product_name": "Product name",
  "result_mode": "Upload",
  "result_mode_code": "upload",
  "document_type": "Blood diagnostics Report",
  "document_type_code": "blood",
  "sample_collection_date": "2026-08-01",
  "report_generation_date": "2026-08-10"
}
```

Use `data.id` as `result_id`. Do not start file uploads until result creation
succeeds.

The backend rejects missing fields, inactive/unassigned products, inactive
providers or assignments, and product/type mismatches.

## 10. Upload Documents One by One

```http
POST /programs/program-services/results/:result_id/documents/
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=<browser_generated_boundary>
```

Multipart fields:

```text
file=<binary_file>                   required
document_category=<report|raw>      required
```

Do not submit `document_type`. It belongs to the result and is inherited by
every uploaded file.

Only one file is accepted per request. The browser or HTTP client must generate
the multipart boundary.

Relevant document response:

```json
{
  "id": "<document_uuid>",
  "result": {
    "id": "<result_uuid>",
    "provider_name": "Provider name",
    "product_name": "Product name",
    "result_mode": "Upload",
    "result_mode_code": "upload",
    "document_type": "Blood diagnostics Report",
    "document_type_code": "blood",
    "sample_collection_date": "2026-08-01",
    "report_generation_date": "2026-08-10"
  },
  "file": "<file_url>",
  "filename": "report.pdf",
  "content_type": "application/pdf",
  "document_category": "Report file",
  "document_category_code": "report"
}
```

Document type is not duplicated at the document's top level.

## 11. Upload State and Completion

```ts
type DocumentUploadStatus =
  | "queued"
  | "uploading"
  | "succeeded"
  | "failed";

interface DocumentUploadItem {
  client_id: string;
  file: File;
  document_category: "report" | "raw";
  status: DocumentUploadStatus;
  document_id?: string;
  error?: string;
}
```

Track every file independently. A failed file can be retried without repeating
successful uploads. The API does not provide chunked or resumable uploads.

After the first document is created, the result's product and document type are
locked. Dates remain editable.

## 12. List Results

```http
GET /programs/program-services/assessment-services/:program_service_id/results/
Authorization: Bearer <access_token>
```

Supported query parameters:

| Parameter | Meaning |
|---|---|
| `page` | Page number |
| `limit` | Page size, maximum 50 |
| `product` | Exact product UUID |

Results are newest first. List records expose the selected product, result-level
document type and code, dates, audit fields, and annotated `documents_count`.

## 13. Errors

| Status | Meaning | Frontend behavior |
|---|---|---|
| `400` | Missing/invalid metadata, disallowed type, inactive mutation target, or invalid upload | Show field or operation error without advancing the workflow |
| `401` | Authentication failed | Start authentication recovery |
| `403` | Account is not an administrator or associate | Show access denied |
| `404` | ProgramService, product metadata resource, result, or document was not found | Stop the affected stage and refresh its parent data |
| `500` | Unexpected server or storage failure | Preserve user input and allow retry where safe |

Changing `product_id` or `document_type` after files exist returns `400`.

## 14. Cache Invalidation

After result creation, invalidate the ProgramService result list.

After each document upload or deletion, invalidate:

- the result-specific document list;
- the ProgramService-wide document list;
- the result detail and result list;
- the assessment ProgramService detail containing `documents_count`.

Allowed-document metadata can be cached by product UUID and does not need
invalidation after result or document mutations.

## 15. Acceptance Criteria

- Upload controls are disabled for an inactive ProgramService.
- Provider options come only from the ProgramService provider endpoint.
- Product options come only from the ProgramService product endpoint and use
  the selected provider's code filter.
- Allowed document types are loaded after product selection.
- Result creation always sends both `product_id` and `document_type`.
- Every file upload sends only `file` and `document_category`.
- Files are uploaded and retried independently.
- Completion is a frontend state; no finalize request is sent.
- Result lists are refreshed after upload completion.
- Product/type edits are disabled once the first document exists.
- Document type is read from the result or nested result, never from a
  top-level document field.
