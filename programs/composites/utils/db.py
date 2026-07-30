from uuid import UUID

from django.db.models import (
    BooleanField,
    Case,
    Count,
    Exists,
    OuterRef,
    Prefetch,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from accounts.customers.models import CustomerCenterAssignment
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
from programs.services.models import CenterServiceAssignment, Service
from programs.services.utils.constants import ServiceCategory


def get_composite_template_for_assignment(
        composite_template_identifier: UUID,
) -> CompositeTemplate | None:
    assignment_services = (
        CompositeTemplateService.objects.filter(
            is_active=True,
            service__is_active=True,
        )
        .select_related("service")
        .order_by("created_at")
    )
    return (
        CompositeTemplate.objects.filter(
            pk=composite_template_identifier,
            is_active=True,
        )
        .prefetch_related(
            Prefetch(
                "services",
                queryset=assignment_services,
                to_attr="assignment_services",
            )
        )
        .first()
    )


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
        service_quantities: dict,
) -> None:
    services_by_category = {
        service_category: []
        for service_category in SERVICE_EXTENSION_CREATORS
    }
    for program_service in program_services:
        services_by_category[
            program_service.service.service_category
        ].append(
            {
                "program_service": program_service,
                "quantity": service_quantities.get(program_service.service.pk),
            }
        )
    for service_category, extension_creator in SERVICE_EXTENSION_CREATORS.items():
        extension_creator(services_by_category[service_category])


def get_composite_program_service_queryset(
        center_id: UUID | str | None = None,
) -> QuerySet[ProgramService]:
    program_services = ProgramService.objects.select_related(
        "service",
        "created_by",
        "cancelled_by",
        "therapy_service",
        "assessment_service",
        "consultation_service",
    )

    center_service_assignment = CenterServiceAssignment.objects.filter(
        service=OuterRef("service"),
        center__pk=center_id,
        is_active=True,
        center__is_active=True,
    )
    return program_services.annotate(
        can_redeem=Case(
            When(service__is_global=True, then=Value(True)),
            default=Exists(center_service_assignment),
            output_field=BooleanField(),
        )
    )


def get_composite_program_queryset(
        center_id: UUID | str | None = None,
) -> QuerySet[CompositeProgram]:
    primary_center_assignments = CustomerCenterAssignment.objects.filter(
        is_primary=True
    ).select_related("center")
    qs = (
        CompositeProgram.objects.select_related(
            "program",
            "program__center",
            "program__created_by",
            "program__cancelled_by",
            "program__customer_profile__customer__user",
            "composite_template",
        )
        .prefetch_related(
            "program__redeemable_centers",
            Prefetch(
                "program__program_services",
                queryset=get_composite_program_service_queryset(center_id)[:3],
                to_attr="service_preview",
            ),
            Prefetch(
                "program__customer_profile__center_assignments",
                queryset=primary_center_assignments,
                to_attr="primary_center_assignments",
            ),
        )
    )
    return qs
