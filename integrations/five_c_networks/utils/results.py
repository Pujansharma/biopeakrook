import arrow
from django.core.files.base import ContentFile
from django.utils import timezone

from core.utils.log import logger
from integrations.five_c_networks.utils.helper import process_evo_report_fetch
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
from programs.services.models import ServiceDocument, ServiceResult
from programs.services.utils.constants import (
    ResultRequestStatus,
    ServiceDocumentCategory,
    ServiceDocumentType,
    ServiceResultMode,
)


def _mark_evo_result_request_failed(result_request, error_message):
    logger.error(
        f"EVO 360 result fetch failed: "
        f"result_request_id={result_request.pk} error={error_message}"
    )
    result_request.status = ResultRequestStatus.FAILED
    result_request.failure_detail = error_message
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


def _process_evo_result_data(
        metadata,
        pdf_report,
        result_request
):
    program_service = result_request.program_service
    program_identifier = program_service.program.pk
    logger.info(
        f"EVO 360 result persistence started: "
        f"result_request_id={result_request.pk}"
    )

    service_result, _ = ServiceResult.objects.update_or_create(
        result_request=result_request,
        document_type=ServiceDocumentType.EVO_360,
        defaults={
            "program_service": program_service,
            "product": result_request.product,
            "provider_name": result_request.product.provider.name,
            "product_name": result_request.product.name,
            "result_mode": ServiceResultMode.FETCH,
            "data": metadata,
            "created_by": result_request.created_by,
        },
    )

    file_name = (
        f"EVO_360_Report_{result_request.pk.hex[:8]}_"
        f"{int(arrow.now().timestamp())}.pdf"
    )
    file_content = pdf_report.getvalue()
    file = ContentFile(content=file_content, name=file_name)
    documents = [
        ServiceDocument(
            result=service_result,
            file=file,
            filename=file_name,
            content_type="application/pdf",
            file_hash=generate_file_hash(file_content),
            document_category=ServiceDocumentCategory.REPORT,
        )
    ]
    ServiceDocument.objects.bulk_create(documents)
    update_result_documents_count(service_result.pk)
    update_program_service_results_count(program_service.pk)
    update_program_service_document_counts(program_service.pk)
    update_composite_program_results_count(program_identifier)
    update_composite_program_document_counts(program_identifier)

    logger.info(
        f"EVO 360 result persistence completed: "
        f"result_request_id={result_request.pk} "
        f"service_result_id={service_result.pk}"
    )
    return service_result


def handle_evo_report_fetch(result_request, provider_api_data):
    logger.info(
        f"EVO 360 result fetch handler started: "
        f"result_request_id={result_request.pk}"
    )
    client_id = provider_api_data.get("client_id", "")
    if not client_id:
        _mark_evo_result_request_failed(
            result_request=result_request,
            error_message="Client ID is missing in provider configuration",
        )
        return None

    client_secret = provider_api_data.get("client_secret", "")
    if not client_secret:
        _mark_evo_result_request_failed(
            result_request=result_request,
            error_message="Client secret is missing in provider configuration",
        )
        return None

    center_id = provider_api_data.get("center_id", "")
    if not center_id:
        _mark_evo_result_request_failed(
            result_request=result_request,
            error_message="Center ID is missing in provider configuration",
        )
        return None

    profile_data = result_request.profile_data or {}
    email = profile_data.get("email", "")
    if not email:
        _mark_evo_result_request_failed(
            result_request=result_request,
            error_message="Email not provided",
        )
        return None

    metadata, result_files, error = process_evo_report_fetch(
        client_id=client_id,
        client_secret=client_secret,
        center_id=center_id,
        email=email,
    )
    if error:
        _mark_evo_result_request_failed(
            result_request=result_request,
            error_message=error,
        )
        return None

    pdf_report, = result_files
    if not pdf_report:
        _mark_evo_result_request_failed(
            result_request=result_request,
            error_message="EVO 360 report file was not available",
        )
        return None

    service_result = _process_evo_result_data(
        metadata=metadata,
        pdf_report=pdf_report,
        result_request=result_request,
    )
    result_request.status = ResultRequestStatus.COMPLETED
    result_request.failure_detail = ""
    result_request.completed_at = timezone.localtime()
    result_request.save(
        update_fields=[
            "status",
            "failure_detail",
            "completed_at",
            "updated_at",
        ]
    )
    logger.info(
        f"EVO 360 result fetch handler completed: "
        f"result_request_id={result_request.pk} "
        f"service_result_id={service_result.pk}"
    )
    return None
