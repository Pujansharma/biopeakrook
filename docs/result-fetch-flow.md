# Result Fetch Flow

This document defines the backend structure for fetching assessment results from
external providers. BugSpeaks is the reference implementation.

## Layer boundaries

Keep provider communication, response normalization, and Django persistence in
separate layers.

| Layer | Location | Responsibility | Django models allowed |
|---|---|---|---|
| Provider SDK | `integrations/<provider>/sdk.py` | Make HTTP requests and return provider responses or file streams | No |
| Integration helper | `integrations/<provider>/tasks.py` | Coordinate SDK calls, validate provider responses, and normalize metadata | No |
| Provider result handler | `integrations/<provider>/utils/results.py` | Interpret normalized provider data, create results and documents, update request status, and refresh counters | Yes |
| Provider product registry | `integrations/<provider>/utils/__init__.py` | Map each supported product callback to that provider's result handler | Yes |
| Central provider registry | `programs/program_services/utils/results.py` | Map provider callbacks to provider-owned product registries and resolve handlers | Yes |
| Dispatcher | `programs/program_services/utils/tasks.py` | Resolve the provider/product handler and run it for a queued request | Yes |
| API serializer | `programs/program_services/serializers.py` | Validate create/refetch requests and initiate dispatch | Yes |

The important boundary is:

```text
SDK functions
    -> model-free integration helper
        -> provider-owned model-aware result handler
            -> ServiceResult and ServiceDocument rows
```

Do not import Django models into provider SDK or integration-helper modules.
Provider-specific HTTP and response-shape knowledge should not leak into the
shared dispatcher or central registry. The provider-owned result handler may
use Django models because it owns persistence for that provider's normalized
response.

## Standard fetch sequence

1. The API creates a `ResultRequest` with `queued` status.
2. `start_result_request_task()` starts the request worker.
3. The worker claims the queued request and changes its status to `running`.
4. The dispatcher resolves the provider registry, then the product handler,
   using the provider and product callbacks.
5. The result handler passes credentials and request identifiers to the
   model-free integration helper.
6. The integration helper calls SDK functions and returns normalized metadata,
   a provider-specific collection of file streams, and an optional error
   message.
7. The result handler creates the `ServiceResult` and its `ServiceDocument`
   rows.
8. The result handler refreshes persisted result, program-service, and composite
   counters.
9. The result handler marks the request `completed`. Expected failures mark it
   `failed` with a failure message.

## SDK function contract

SDK functions own only external communication. They should:

- construct and send the provider request;
- evaluate the HTTP response;
- return decoded JSON, raw bytes, or an in-memory file stream;
- return a provider-facing error value for expected failures;
- avoid model queries, model updates, and application counter maintenance.

Example:

```python
import io

import requests


def get_provider_record(api_key: str, external_id: str):
    response = requests.get(
        "https://provider.example/api/results/",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"external_id": external_id},
    )
    if not response.ok:
        return None, "Failed to retrieve provider record"
    return response.json(), None


def get_provider_report(api_key: str, external_id: str):
    response = requests.get(
        "https://provider.example/api/report/",
        headers={"Authorization": f"Bearer {api_key}"},
        params={"external_id": external_id},
    )
    if not response.ok:
        return None, "Failed to retrieve provider report"
    return io.BytesIO(response.content), None
```

## Integration-helper contract

The integration helper coordinates one or more SDK functions and normalizes the
provider response. It remains model-free.

Use this three-item return contract:

```text
(metadata, files, error)
```

- `metadata` is a normalized dictionary or `None`.
- `files` is an ordered collection of file streams.
- `error` is `None` on success or a user-safe message for an expected failure.

Only the top-level three-item contract is fixed. The `files` collection may
contain one, two, or any number of files. Its cardinality and ordering are
provider-specific and must be documented by that provider's integration helper.
The corresponding result handler owns the interpretation of those files.

Example:

```python
from integrations.example_provider.sdk import (
    get_provider_record,
    get_provider_report,
)


def process_provider_report_fetch(api_key: str, external_id: str):
    record, error = get_provider_record(api_key, external_id)
    if error:
        return None, [], "Failed to retrieve provider result"

    data = record.get("data") or {}
    if not data:
        return None, [], "No provider result data received"

    metadata = {
        "provider_name": data.get("provider_name"),
        "sample_collection_date": data.get("sample_collection_date"),
        "report_generation_date": data.get("report_generation_date"),
    }

    report_file, error = get_provider_report(api_key, external_id)
    if error:
        return metadata, [], "Failed to retrieve provider report file"
    return metadata, [report_file], None
```

The helper must not create `ContentFile`, `ServiceResult`, `ServiceDocument`, or
`ResultRequest` objects. It must not update counters or statuses.

### BugSpeaks helper contract

`integrations/bugspeaks/tasks.py` provides the model-free
`process_bugspeaks_report_fetch()` reference helper. It first retrieves and
normalizes the BugSpeaks record metadata, then asks the SDK for the result
files. Its ordered file collection is:

```text
(PDF report, additional XLSX report)
```

The BugSpeaks SDK treats either missing file as an expected fetch failure and
returns placeholder file values with an error. The provider result handler in
`integrations/bugspeaks/utils/results.py` owns the interpretation and
persistence of this ordered pair.

## Result-handler contract

Result handlers are provider-owned, model-aware persistence functions in
`integrations/<provider>/utils/results.py`. The standard signature is:

```python
def handle_provider_report_fetch(
        result_request: ResultRequest, provider_api_data: dict
) -> None:
```

The handler should:

- validate required provider configuration and request data;
- call the model-free integration helper;
- mark expected failures on `ResultRequest`;
- create a fresh `ServiceResult`;
- convert returned bytes or streams to `ContentFile` objects;
- create `ServiceDocument` rows with normal model `create()` calls;
- compute file hashes from the original bytes;
- update all persisted counters;
- mark successful requests as completed using `timezone.localtime()`.

Example persistence section:

```python
file_content = report_file.getvalue()
file_name = f"Provider_Report_{external_id}.pdf"
file = ContentFile(content=file_content, name=file_name)

service_result = ServiceResult.objects.create(
    result_request=result_request,
    program_service=result_request.program_service,
    product=result_request.product,
    provider_name=metadata.get("provider_name"),
    result_mode=ServiceResultMode.FETCH,
    document_type=ServiceDocumentType.OTHER,
    sample_collection_date=metadata.get("sample_collection_date"),
    report_generation_date=metadata.get("report_generation_date"),
    created_by=result_request.created_by,
)

ServiceDocument.objects.create(
    result=service_result,
    file=file,
    filename=file_name,
    content_type="application/pdf",
    file_hash=generate_file_hash(file_content),
    document_category=ServiceDocumentCategory.REPORT,
)

program_service = result_request.program_service
update_result_documents_count(service_result.pk)
update_program_service_results_count(program_service.pk)
update_program_service_document_counts(program_service.pk)
update_composite_program_results_count(program_service.program.pk)
update_composite_program_document_counts(program_service.program.pk)

result_request.status = ResultRequestStatus.COMPLETED
result_request.completed_at = timezone.localtime()
result_request.save(
    update_fields=["status", "completed_at", "updated_at"]
)
```

Do not add `transaction.atomic()` inside provider integration helpers or result
handler functions unless explicitly required. Transaction boundaries belong at
the API operation layer when needed.

## Handler registration

Handler lookup uses two registry levels. A provider integration first maps its
supported product callbacks to provider-owned result handlers:

```python
from products.utils.constants import ProductCallbackFunction

from .results import handle_example_provider_report_fetch


EXAMPLE_PROVIDER_HANDLER = {
    ProductCallbackFunction.EXAMPLE_PRODUCT: handle_example_provider_report_fetch,
}
```

The shared registry then maps the provider callback to that provider-owned
product registry:

```python
from integrations.example_provider.utils import EXAMPLE_PROVIDER_HANDLER
from products.utils.constants import ProviderCallbackFunction


PROVIDER_HANDLER = {
    ProviderCallbackFunction.EXAMPLE_PROVIDER: EXAMPLE_PROVIDER_HANDLER,
}
```

BugSpeaks follows this structure with `BUGSPEAKS_HANDLER` in
`integrations/bugspeaks/utils/__init__.py` and its entry in `PROVIDER_HANDLER`.
`get_result_fetch_handler()` returns `None` when the provider callback is not
registered. For a registered provider with an unregistered product callback,
the current resolver returns a no-op callable. Consequently, serializer
validation rejects an unknown provider registry, but does not reject that
known-provider/unknown-product case.

## Refetch flow

A refetch reuses the existing `ResultRequest` but deletes the results produced
for that request before starting a new fetch.

```python
ServiceResult.objects.filter(result_request=result_request).delete()
```

Deleting the `ServiceResult` rows cascades to their related `ServiceDocument`
database rows. No semantic result rows are retained. Physical file deletion
from storage is outside this flow.

After deletion:

1. Reset the request to `queued`.
2. Clear `failure_detail`, `started_at`, and `completed_at`.
3. Recompute the program-service result and document counters.
4. Recompute composite result and document counters where applicable.
5. Start the request worker again.

Counters must be recomputed from remaining rows rather than assigned directly to
zero because the program service may contain results from other requests or
manual uploads.

## Cancellation flow

`POST result-requests/<uuid:pk>/cancel/` accepts an empty request body. The
cancel serializer changes only the persisted request status to `cancelled` and
saves `status` and `updated_at`; it does not delete results or documents.

Completed requests cannot be cancelled, and an already-cancelled request raises
a validation error. Queued, running, and failed requests may be changed to
cancelled. Cancellation does not coordinate with the request worker.

## Implementation checklist

- SDK module contains no model imports.
- Integration helper contains no model imports.
- Integration helper always returns `metadata, files, error`.
- The `files` value supports the number of files returned by the provider.
- Provider-specific file ordering is documented in the integration helper.
- Provider result handler lives in `integrations/<provider>/utils/results.py`.
- Provider product registry is exported from the integration's `utils` package.
- Central `PROVIDER_HANDLER` contains the provider registry.
- Result handler uses normal model creation for files.
- Result-level document count receives `service_result.pk`.
- Program-service result and document counters are refreshed.
- Composite result and document counters are refreshed.
- Expected failures set request status and `failure_detail`.
- Successful requests set `completed_at` with `timezone.localtime()`.
- Refetch deletes result and document database rows; storage cleanup is not part
  of this flow.
