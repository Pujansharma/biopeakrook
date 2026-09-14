from functools import partial
from uuid import UUID

from django.core.files.storage import Storage
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from programs.composites.utils.db import (
    update_composite_program_document_counts,
    update_composite_program_results_count,
)
from programs.models import ProgramService
from programs.services.models import ResultRequest, ServiceDocument, ServiceResult
from programs.services.utils.constants import (
    ResultRequestStatus,
    ServiceDocumentCategory,
    ServiceResultMode,
)


def update_result_documents_count(result_id: UUID):
    documents_count_subquery = (
        ServiceDocument.objects.filter(
            result=OuterRef("pk"),
        )
        .values("result")
        .annotate(count=Count("pk"))
        .values("count")
    )
    ServiceResult.objects.filter(pk=result_id).update(
        documents_count=Coalesce(
            Subquery(documents_count_subquery),
            Value(0),
        )
    )


def _get_program_service_result_requests_count_subquery(
    excluded_statuses=None,
):
    result_requests = ResultRequest.objects.filter(
        program_service=OuterRef("pk"),
    )
    if excluded_statuses:
        result_requests = result_requests.exclude(status__in=excluded_statuses)
    return (
        result_requests.values("program_service")
        .annotate(count=Count("pk"))
        .values("count")
    )


def _get_program_service_results_count_subquery(result_mode=None):
    filter_arguments = {
        "program_service": OuterRef("pk"),
    }
    if result_mode:
        filter_arguments["result_mode"] = result_mode
    return (
        ServiceResult.objects.filter(**filter_arguments)
        .values("program_service")
        .annotate(count=Count("pk"))
        .values("count")
    )


def update_program_service_results_count(
    program_service_identifier: UUID,
):
    results_count_subquery = _get_program_service_results_count_subquery()
    ProgramService.objects.filter(pk=program_service_identifier).update(
        results_count=Coalesce(
            Subquery(results_count_subquery),
            Value(0),
        )
    )


def _get_program_service_documents_count_subquery(
    document_category=None,
    result_mode=None,
):
    filter_arguments = {
        "result__program_service": OuterRef("pk"),
    }
    if document_category:
        filter_arguments["document_category"] = document_category
    if result_mode:
        filter_arguments["result__result_mode"] = result_mode
    return (
        ServiceDocument.objects.filter(**filter_arguments)
        .values("result__program_service")
        .annotate(count=Count("pk"))
        .values("count")
    )


def update_program_service_document_counts(
    program_service_identifier: UUID,
):
    documents_count_subquery = _get_program_service_documents_count_subquery()
    reports_count_subquery = _get_program_service_documents_count_subquery(
        ServiceDocumentCategory.REPORT
    )
    raw_data_count_subquery = _get_program_service_documents_count_subquery(
        ServiceDocumentCategory.RAW
    )
    ProgramService.objects.filter(pk=program_service_identifier).update(
        documents_count=Coalesce(
            Subquery(documents_count_subquery),
            Value(0),
        ),
        reports_count=Coalesce(
            Subquery(reports_count_subquery),
            Value(0),
        ),
        raw_data_count=Coalesce(
            Subquery(raw_data_count_subquery),
            Value(0),
        ),
    )


def _get_program_service_fetch_count_update_values():
    fetch_count_subquery = _get_program_service_result_requests_count_subquery()
    fetch_results_count_subquery = _get_program_service_results_count_subquery(
        ServiceResultMode.FETCH
    )
    fetch_documents_count_subquery = (
        _get_program_service_documents_count_subquery(
            result_mode=ServiceResultMode.FETCH,
        )
    )
    fetch_pending_count_subquery = (
        _get_program_service_result_requests_count_subquery(
            excluded_statuses=[
                ResultRequestStatus.COMPLETED,
                ResultRequestStatus.FAILED,
                ResultRequestStatus.CANCELLED,
            ]
        )
    )
    return {
        "fetch_count": Coalesce(Subquery(fetch_count_subquery), Value(0)),
        "fetch_results_count": Coalesce(
            Subquery(fetch_results_count_subquery),
            Value(0),
        ),
        "fetch_documents_count": Coalesce(
            Subquery(fetch_documents_count_subquery),
            Value(0),
        ),
        "fetch_pending_count": Coalesce(
            Subquery(fetch_pending_count_subquery),
            Value(0),
        ),
    }


def update_program_service_fetch_counts(
    program_service_identifier: UUID,
):
    ProgramService.objects.filter(pk=program_service_identifier).update(
        **_get_program_service_fetch_count_update_values()
    )


def update_all_result_documents_count():
    documents_count_subquery = (
        ServiceDocument.objects.filter(
            result=OuterRef("pk"),
        )
        .values("result")
        .annotate(count=Count("pk"))
        .values("count")
    )
    return ServiceResult.objects.update(
        documents_count=Coalesce(
            Subquery(documents_count_subquery),
            Value(0),
        )
    )


def update_all_program_service_results_count():
    results_count_subquery = _get_program_service_results_count_subquery()
    return ProgramService.objects.update(
        results_count=Coalesce(
            Subquery(results_count_subquery),
            Value(0),
        )
    )


def update_all_program_service_document_counts():
    documents_count_subquery = _get_program_service_documents_count_subquery()
    reports_count_subquery = _get_program_service_documents_count_subquery(
        ServiceDocumentCategory.REPORT
    )
    raw_data_count_subquery = _get_program_service_documents_count_subquery(
        ServiceDocumentCategory.RAW
    )
    return ProgramService.objects.update(
        documents_count=Coalesce(
            Subquery(documents_count_subquery),
            Value(0),
        ),
        reports_count=Coalesce(
            Subquery(reports_count_subquery),
            Value(0),
        ),
        raw_data_count=Coalesce(
            Subquery(raw_data_count_subquery),
            Value(0),
        ),
    )


def update_all_program_service_fetch_counts():
    return ProgramService.objects.update(
        **_get_program_service_fetch_count_update_values()
    )


def _delete_stored_file(storage: Storage, file_name: str):
    storage.delete(file_name)


def delete_service_document(service_document: ServiceDocument):
    result_identifier = service_document.result.pk
    program_service_identifier = service_document.result.program_service.pk
    program_identifier = service_document.result.program_service.program.pk
    file_storage = service_document.file.storage
    file_name = service_document.file.name

    with transaction.atomic():
        service_document.delete()
        update_result_documents_count(result_identifier)
        update_program_service_document_counts(program_service_identifier)
        update_program_service_fetch_counts(program_service_identifier)
        update_composite_program_document_counts(program_identifier)
        if file_name:
            transaction.on_commit(
                partial(_delete_stored_file, file_storage, file_name)
            )


def delete_service_result(service_result: ServiceResult):
    program_service_identifier = service_result.program_service.pk
    program_identifier = service_result.program_service.program.pk

    with transaction.atomic():
        document_files = [
            (service_document.file.storage, service_document.file.name)
            for service_document in ServiceDocument.objects.filter(
                result=service_result,
            ).only("file")
        ]
        service_result.delete()
        update_program_service_results_count(program_service_identifier)
        update_program_service_document_counts(program_service_identifier)
        update_program_service_fetch_counts(program_service_identifier)
        update_composite_program_results_count(program_identifier)
        update_composite_program_document_counts(program_identifier)
        for file_storage, file_name in document_files:
            if file_name:
                transaction.on_commit(
                    partial(_delete_stored_file, file_storage, file_name)
                )
