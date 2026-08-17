# Product Allowed-Document Metadata — Frontend ePRD

## 1. Purpose

Retrieve the document types allowed for a selected assessment product. The
selected value is stored on `ServiceResult`; it is not submitted with individual
file uploads.

The complete workflow is documented in
`assessment-program-service-result-upload-frontend-eprd.md`.

## 2. Endpoint

```http
GET /products/:product_id/allowed-documents/
Authorization: Bearer <access_token>
```

Administrators and associates can retrieve metadata. Customers cannot.
`X-Center-ID`, request bodies, query parameters, and pagination are not used.

Use the product UUID returned by the assessment ProgramService product selector.

## 3. Response

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

```ts
interface ProductDocumentTypeOption {
  display_name: string;
  value: string;
}
```

Render `display_name` and submit `value` as `document_type` when creating or
editing result metadata.

## 4. Selection Rules

- Product-specific values appear before `Other`.
- `Other` is always the final option and is valid for every product.
- The returned order is authoritative.
- Values are opaque backend codes and must not be derived from labels.
- The frontend must not hardcode provider/product mappings.
- Changing the product clears the current document-type selection and loads
  the new product's metadata.
- Both product and document type are required to create a result.

The backend validates the selected value against the same mapping used by this
endpoint. A stale or forged value is rejected during result creation.

## 5. Result Integration

```http
POST /programs/program-services/assessment-services/:program_service_id/results/
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "product_id": "<product_uuid>",
  "document_type": "blood",
  "sample_collection_date": null,
  "report_generation_date": null
}
```

The result response exposes:

```json
{
  "document_type": "Blood diagnostics Report",
  "document_type_code": "blood"
}
```

After the result receives its first document, product and type are locked.

## 6. File Upload Integration

The file upload request contains no document type:

```text
file=<binary_file>
document_category=<report|raw>
```

Uploaded-document responses expose the inherited type inside their nested
`result`, not at the document's top level.

## 7. State, Caching, and Errors

Cache allowed-document metadata by product UUID. Result/document mutations do
not invalidate this metadata.

| Status | Meaning | Frontend behavior |
|---|---|---|
| `401` | Authentication failed | Start authentication recovery |
| `403` | Account cannot access metadata | Show access denied |
| `404` | Product does not exist | Clear product/type and refresh products |
| `500` | Unexpected failure | Show retry and keep result submission disabled |

## 8. Acceptance Criteria

- Metadata is loaded only after product selection.
- Labels are displayed and values are submitted unchanged.
- Result creation always includes one returned value.
- Product changes clear stale type selection.
- No file upload sends `document_type`.
- Existing results with uploaded files do not offer product/type edits.
