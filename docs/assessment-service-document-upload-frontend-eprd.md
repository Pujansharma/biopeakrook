# Assessment Service Document Upload — Frontend ePRD

## 1. Purpose

Specify the file-only stage of the assessment result workflow. The complete
provider, product, document-type, result, and upload sequence is defined in
`assessment-program-service-result-upload-frontend-eprd.md`.

The result must already exist before this request is sent.

## 2. Endpoint

```http
POST /programs/program-services/results/:result_id/documents/
Authorization: Bearer <access_token>
Content-Type: multipart/form-data; boundary=<browser_generated_boundary>
```

Administrators and associates can upload. Customers cannot. `X-Center-ID` is
not required.

## 3. Payload

Send exactly one file per request:

```text
file=<binary_file>                   required
document_category=<report|raw>      required
```

Do not submit:

- `document_type` or `document_type_code`;
- `filename`;
- `content_type`;
- `file_hash`;
- `result`.

Document type belongs to the parent result. The selected type is returned in
the nested `result` representation.

The browser or HTTP client must generate the multipart boundary.

## 4. Category Values

| Code | Display value |
|---|---|
| `report` | `Report file` |
| `raw` | `Raw data file` |

Use the code in the request and the returned display value in the UI.

## 5. Response Shape

```json
{
  "detail": "Create success.",
  "data": {
    "id": "<document_uuid>",
    "result": {
      "id": "<result_uuid>",
      "provider_name": "<provider_name>",
      "product_name": "<product_name>",
      "result_mode": "Upload",
      "result_mode_code": "upload",
      "document_type": "<document_type_display>",
      "document_type_code": "<document_type_code>",
      "sample_collection_date": "<date|null>",
      "report_generation_date": "<date|null>"
    },
    "file": "<file_url>",
    "filename": "report.pdf",
    "content_type": "application/pdf",
    "document_category": "Report file",
    "document_category_code": "report",
    "is_active": true,
    "created_at": "<ISO-8601_datetime>",
    "updated_at": "<ISO-8601_datetime>"
  }
}
```

There is no top-level document type on `data`.

## 6. Upload Behavior

- Upload files one at a time.
- Track queued, uploading, succeeded, and failed state per file.
- Retry only failed files; do not repeat successful uploads.
- The backend stores the basename and declared content type and calculates the
  file hash internally.
- The API has no chunked, resumable, or finalize operation.
- Result product and document type cannot be changed after the first successful
  document upload.

## 7. Errors and Refreshes

| Status | Meaning |
|---|---|
| `400` | Missing file/category, invalid category, or inactive result ownership |
| `401` | Authentication failed |
| `403` | Account cannot upload |
| `404` | Result does not exist or is not an assessment result |
| `500` | Unexpected server or storage failure |

After success, invalidate the result detail/list, result document list,
ProgramService document list, and ProgramService detail.

## 8. Acceptance Criteria

- A result UUID exists before upload begins.
- Every request carries one file and one category.
- No document-type field is submitted with a file.
- Type display and code are read from the nested result.
- Per-file retries do not restart successful uploads.
- The frontend sends no finalize request.
