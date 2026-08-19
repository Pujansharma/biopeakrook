from uuid import UUID

from django.db.models import (
    Count,
    OuterRef,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce

from programs.composites.models import (
    CompositeServicePrerequisite,
    CompositeTemplate,
    CompositeTemplateService,
)
from programs.models import (
    AssessmentProgramService,
    CompositeProgram,
    ConsultationProgramService,
    ProgramService,
    TherapyProgramService,
)
from programs.services.models import Service, ServiceDocument, ServiceResult
from programs.services.utils.constants import (
    ServiceCategory,
    ServiceDocumentCategory,
)
from programs.utils.constants import ServiceAssignment


def update_composite_template_services_count(
        composite_template_id: UUID,
) -> None:
    service_count = (
        CompositeTemplateService.objects.filter(
            composite_template=OuterRef("pk"),
            is_active=True,
        )
        .values("composite_template")
        .annotate(count=Count("pk"))
        .values("count")
    )
    assessment_services_count = (
        Service.objects.filter(
            template_services__composite_template=OuterRef("pk"),
            template_services__is_active=True,
            service_category=ServiceCategory.ASSESSMENT,
        )
        .values("template_services__composite_template")
        .annotate(count=Count("pk"))
        .values("count")
    )
    therapy_services_count = (
        Service.objects.filter(
            template_services__composite_template=OuterRef("pk"),
            template_services__is_active=True,
            service_category=ServiceCategory.THERAPY,
        )
        .values("template_services__composite_template")
        .annotate(count=Count("pk"))
        .values("count")
    )
    consultation_services_count = (
        Service.objects.filter(
            template_services__composite_template=OuterRef("pk"),
            template_services__is_active=True,
            service_category=ServiceCategory.CONSULTATION,
        )
        .values("template_services__composite_template")
        .annotate(count=Count("pk"))
        .values("count")
    )

    CompositeTemplate.objects.filter(pk=composite_template_id).update(
        services_count=Coalesce(Subquery(service_count), Value(0)),
        assessment_services_count=Coalesce(
            Subquery(assessment_services_count), Value(0)
        ),
        therapy_services_count=Coalesce(
            Subquery(therapy_services_count), Value(0)
        ),
        consultation_services_count=Coalesce(
            Subquery(consultation_services_count), Value(0)
        ),
    )


def update_composite_program_service_counts(
        program_id: UUID,
) -> None:
    add_ons_count = (
        ProgramService.objects.filter(
            program=OuterRef("program"),
            assignment_type=ServiceAssignment.ADD_ON,
        )
        .values("program")
        .annotate(count=Count("pk"))
        .values("count")
    )
    assessment_services_count = (
        ProgramService.objects.filter(
            program=OuterRef("program"),
            service__service_category=ServiceCategory.ASSESSMENT,
        )
        .values("program")
        .annotate(count=Count("pk"))
        .values("count")
    )
    therapy_services_count = (
        ProgramService.objects.filter(
            program=OuterRef("program"),
            service__service_category=ServiceCategory.THERAPY,
        )
        .values("program")
        .annotate(count=Count("pk"))
        .values("count")
    )
    consultation_services_count = (
        ProgramService.objects.filter(
            program=OuterRef("program"),
            service__service_category=ServiceCategory.CONSULTATION,
        )
        .values("program")
        .annotate(count=Count("pk"))
        .values("count")
    )
    CompositeProgram.objects.filter(program__pk=program_id).update(
        add_ons_count=Coalesce(Subquery(add_ons_count), Value(0)),
        assessment_services_count=Coalesce(
            Subquery(assessment_services_count),
            Value(0),
        ),
        therapy_services_count=Coalesce(
            Subquery(therapy_services_count),
            Value(0),
        ),
        consultation_services_count=Coalesce(
            Subquery(consultation_services_count),
            Value(0),
        ),
    )


def _get_composite_program_results_count_subquery():
    return (
        ServiceResult.objects.filter(
            program_service__program=OuterRef("program"),
        )
        .values("program_service__program")
        .annotate(count=Count("pk"))
        .values("count")
    )


def update_composite_program_results_count(
        program_identifier: UUID,
):
    results_count_subquery = _get_composite_program_results_count_subquery()
    CompositeProgram.objects.filter(program__pk=program_identifier).update(
        results_count=Coalesce(
            Subquery(results_count_subquery),
            Value(0),
        )
    )


def _get_composite_program_documents_count_subquery(document_category=None):
    filter_arguments = {
        "result__program_service__program": OuterRef("program"),
    }
    if document_category:
        filter_arguments["document_category"] = document_category
    return (
        ServiceDocument.objects.filter(**filter_arguments)
        .values("result__program_service__program")
        .annotate(count=Count("pk"))
        .values("count")
    )


def update_composite_program_document_counts(
        program_identifier: UUID,
):
    documents_count_subquery = _get_composite_program_documents_count_subquery()
    reports_count_subquery = _get_composite_program_documents_count_subquery(
        ServiceDocumentCategory.REPORT
    )
    raw_data_count_subquery = _get_composite_program_documents_count_subquery(
        ServiceDocumentCategory.RAW
    )
    CompositeProgram.objects.filter(program__pk=program_identifier).update(
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


def update_all_composite_program_results_count():
    results_count_subquery = _get_composite_program_results_count_subquery()
    return CompositeProgram.objects.update(
        results_count=Coalesce(
            Subquery(results_count_subquery),
            Value(0),
        )
    )


def update_all_composite_program_document_counts():
    documents_count_subquery = _get_composite_program_documents_count_subquery()
    reports_count_subquery = _get_composite_program_documents_count_subquery(
        ServiceDocumentCategory.REPORT
    )
    raw_data_count_subquery = _get_composite_program_documents_count_subquery(
        ServiceDocumentCategory.RAW
    )
    return CompositeProgram.objects.update(
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


def update_prerequisite_related_service_count(
        service_id: UUID,
) -> None:
    related_services_count = (
        CompositeTemplateService.objects.filter(
            related_prerequisites=OuterRef("pk"),
        )
        .values("related_prerequisites")
        .annotate(count=Count("pk"))
        .values("count")
    )
    CompositeServicePrerequisite.objects.filter(
        template_service__pk=service_id
    ).update(
        related_services_count=Coalesce(
            Subquery(related_services_count),
            Value(0),
        )
    )


def create_therapy_program_services(
        program_service_data: list[dict],
) -> None:
    TherapyProgramService.objects.bulk_create(
        [
            TherapyProgramService(
                program_service=service_data["program_service"],
                sessions_count=service_data["quantity"],
            )
            for service_data in program_service_data
        ]
    )


def create_assessment_program_services(
        program_service_data: list[dict],
) -> None:
    AssessmentProgramService.objects.bulk_create(
        [
            AssessmentProgramService(
                program_service=service_data["program_service"]
            )
            for service_data in program_service_data
        ]
    )


def create_consultation_program_services(
        program_service_data: list[dict],
) -> None:
    ConsultationProgramService.objects.bulk_create(
        [
            ConsultationProgramService(
                program_service=service_data["program_service"]
            )
            for service_data in program_service_data
        ]
    )


SERVICE_EXTENSION_CREATORS = {
    ServiceCategory.THERAPY: create_therapy_program_services,
    ServiceCategory.ASSESSMENT: create_assessment_program_services,
    ServiceCategory.CONSULTATION: create_consultation_program_services,
}


def create_program_service_extensions(
        program_services: list[ProgramService],
        service_quantities: list[int | None],
):
    services_by_category = {
        service_category: []
        for service_category in SERVICE_EXTENSION_CREATORS
    }
    for program_service, service_quantity in zip(
            program_services,
            service_quantities,
            strict=True,
    ):
        services_by_category[
            program_service.service.service_category
        ].append(
            {
                "program_service": program_service,
                "quantity": service_quantity,
            }
        )
    for service_category, extension_creator in SERVICE_EXTENSION_CREATORS.items():
        extension_creator(services_by_category[service_category])
