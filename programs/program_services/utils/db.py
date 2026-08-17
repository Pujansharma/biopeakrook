from functools import partial
from uuid import UUID

from django.core.files.storage import Storage
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from programs.models import ProgramService
from programs.services.models import ServiceDocument, ServiceResult
from programs.services.utils.constants import ServiceDocumentCategory


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


def update_program_service_results_count(
    program_service_identifier: UUID,
):
    results_count_subquery = (
        ServiceResult.objects.filter(
            program_service=OuterRef("pk"),
        )
        .values("program_service")
        .annotate(count=Count("pk"))
        .values("count")
    )
    ProgramService.objects.filter(pk=program_service_identifier).update(
        results_count=Coalesce(
            Subquery(results_count_subquery),
            Value(0),
        )
    )


def _get_program_service_documents_count_subquery(document_category=None):
    filter_kwargs = {
        "result__program_service": OuterRef("pk"),
    }
    if document_category:
        filter_kwargs["document_category"] = document_category
    return (
        ServiceDocument.objects.filter(**filter_kwargs)
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
    results_count_subquery = (
        ServiceResult.objects.filter(
            program_service=OuterRef("pk"),
        )
        .values("program_service")
        .annotate(count=Count("pk"))
        .values("count")
    )
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


def _delete_stored_file(storage: Storage, file_name: str):
    storage.delete(file_name)


def delete_service_document(service_document: ServiceDocument):
    result_identifier = service_document.result.pk
    program_service_identifier = service_document.result.program_service.pk
    file_storage = service_document.file.storage
    file_name = service_document.file.name

    with transaction.atomic():
        service_document.delete()
        update_result_documents_count(result_identifier)
        update_program_service_document_counts(program_service_identifier)
        if file_name:
            transaction.on_commit(
                partial(_delete_stored_file, file_storage, file_name)
            )


def delete_service_result(service_result: ServiceResult):
    program_service_identifier = service_result.program_service.pk

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
        for file_storage, file_name in document_files:
            if file_name:
                transaction.on_commit(
                    partial(_delete_stored_file, file_storage, file_name)
                )
