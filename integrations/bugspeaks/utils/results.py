import arrow
from django.core.files.base import ContentFile
from django.utils import timezone

from core.utils.log import logger
from integrations.bugspeaks.tasks import process_bugspeaks_report_fetch
from programs.composites.utils.db import (
    update_composite_program_document_counts,
    update_composite_program_results_count,
)
from programs.program_services.utils.db import (
    update_program_service_document_counts,
    update_program_service_results_count,
    update_result_documents_count,
)
from programs.program_services.utils.helper import generate_file_hash
from programs.services.models import ResultRequest, ServiceDocument, ServiceResult
from programs.services.utils.constants import (
    ResultRequestStatus,
    ServiceDocumentCategory,
    ServiceDocumentType,
    ServiceResultMode,
)


def handle_bugspeaks_report_fetch(result_request: ResultRequest, provider_api_data: dict) -> None:
    """Fetch and persist the files for a BugSpeaks result request.

    This function is the reference flow for provider-backed result fetch
    handlers. It validates the required provider and request data, delegates
    remote API access to the BugSpeaks integration, creates one fetched
    ``ServiceResult`` with its report and raw-data documents, refreshes all
    affected result and program counters, and marks the request as completed.

    Expected provider or request failures mark ``result_request`` as failed
    and return without creating result records. Unexpected integration,
    storage, or database exceptions propagate to the calling request thread.

    Args:
        result_request: Persisted request containing the program service,
            product, creator, and ``data["bugspeaks_id"]``.
        provider_api_data: Provider configuration containing ``api_key``.

    Returns:
        None.
    """
    api_key = provider_api_data.get('api_key', "")

    if not api_key:
        _message = "API key is missing in provider configuration"
        logger.error(_message)
        result_request.status = ResultRequestStatus.FAILED
        result_request.failure_detail = _message
        result_request.completed_at = timezone.localtime()
        result_request.save(
            update_fields=[
                "status",
                "failure_detail",
                "completed_at",
                "updated_at",
            ]
        )
        return None

    _data = result_request.data or {}

    bugspeaks_id = _data.get('bugspeaks_id', "")
    if not bugspeaks_id:
        _message = "Bugspeaks ID not provided"
        logger.error(_message)
        result_request.status = ResultRequestStatus.FAILED
        result_request.failure_detail = _message
        result_request.completed_at = timezone.localtime()
        result_request.save(
            update_fields=[
                "status",
                "failure_detail",
                "completed_at",
                "updated_at",
            ]
        )
        return None

    metadata, result_files, error = process_bugspeaks_report_fetch(api_key, bugspeaks_id)

    if error:
        logger.error(f"API Error: {error}")
        result_request.status = ResultRequestStatus.FAILED
        result_request.failure_detail = error
        result_request.completed_at = timezone.localtime()
        result_request.save(
            update_fields=[
                "status",
                "failure_detail",
                "completed_at",
                "updated_at",
            ]
        )
        return None

    if len(result_files) < 2:
        logger.warning("Files are missing, expected 2, received 1.")

    _pdf_report, _raw_file = result_files
    program_service = result_request.program_service
    program_identifier = program_service.program.pk

    service_result, _ = ServiceResult.objects.update_or_create(
        result_request=result_request,
        program_service=program_service,
        defaults={
            "product": result_request.product,
            "provider_name": result_request.product.provider.name,
            "product_name": result_request.product.name,
            "result_mode": ServiceResultMode.FETCH,
            "document_type": ServiceDocumentType.BUGSPEAKS_REPORT,
            "sample_collection_date": metadata.get("sample_pickup_date"),
            "report_generation_date": metadata.get("project_completed_timestamp"),
            "created_by": result_request.created_by,
        }
    )

    documents = []

    if _pdf_report:
        file_name = (
            f"BugSpeaks_PDF_Report_{bugspeaks_id}_"
            f"{int(arrow.now().timestamp())}.pdf"
        )
        file_content = _pdf_report.getvalue()
        file = ContentFile(content=file_content, name=file_name)
        documents.append(
            ServiceDocument(
                result=service_result,
                file=file,
                filename=file_name,
                content_type="application/pdf",
                file_hash=generate_file_hash(file_content),
                document_category=ServiceDocumentCategory.REPORT,
            )
        )

    if _raw_file:
        file_name = (
            f"BugSpeaks_Additional_Report_{bugspeaks_id}_"
            f"{int(arrow.now().timestamp())}.xlsx"
        )
        file_content = _raw_file.getvalue()
        file = ContentFile(content=file_content, name=file_name)
        documents.append(
            ServiceDocument(
                result=service_result,
                file=file,
                filename=file_name,
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                file_hash=generate_file_hash(file_content),
                document_category=ServiceDocumentCategory.RAW,
            )
        )
    ServiceDocument.objects.bulk_create(documents)
    update_result_documents_count(service_result.pk)
    update_program_service_results_count(program_service.pk)
    update_program_service_document_counts(program_service.pk)
    update_composite_program_results_count(program_identifier)
    update_composite_program_document_counts(program_identifier)

    result_request.status = ResultRequestStatus.COMPLETED
    result_request.completed_at = timezone.localtime()
    result_request.save(
        update_fields=["status", "completed_at", "updated_at"]
    )
    return None
