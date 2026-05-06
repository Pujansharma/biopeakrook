from uuid import UUID

from django.db.models import F, Value, Case, When, Subquery, OuterRef, Sum, Count
from django.db.models.functions import Coalesce

from accounts.centers.models import Center
from services.programs.models import Program, ProgramService


def increment_program_service_sessions_used(program_service_id) -> None:
    ProgramService.objects.filter(pk=program_service_id).update(
        sessions_used=F("sessions_used") + 1
    )
    Program.objects.filter(program_services__pk=program_service_id).update(
        sessions_used=F("sessions_used") + 1
    )


def decrement_program_service_sessions_used(program_service_id) -> None:
    ProgramService.objects.filter(pk=program_service_id).update(
        sessions_used=Case(
            When(sessions_used__gt=0, then=F("sessions_used") - 1),
            default=Value(0),
        )
    )
    Program.objects.filter(program_services__pk=program_service_id).update(
        sessions_used=Case(
            When(sessions_used__gt=0, then=F("sessions_used") - 1),
            default=Value(0),
        )
    )


def increment_program_sessions_count(program_id, sessions_count: int) -> None:
    Program.objects.filter(pk=program_id).update(
        sessions_count=F("sessions_count") + sessions_count
    )


def decrement_program_sessions_count(program_id, sessions_count: int) -> None:
    Program.objects.filter(pk=program_id).update(
        sessions_count=Case(
            When(
                sessions_count__gte=sessions_count,
                then=F("sessions_count") - sessions_count,
            ),
            default=Value(0),
        )
    )


def update_program_services_count(program_id: UUID) -> None:
    subquery = (
        ProgramService.objects.filter(program_id=OuterRef("pk"))
        .values("program_id")
        .annotate(count=Count("pk"))
        .values("count")
    )
    Program.objects.filter(pk=program_id).update(
        services_count=Coalesce(Subquery(subquery), Value(0))
    )


def update_program_redeemable_centers_count(program_id: UUID) -> None:
    subquery = (
        Center.objects.filter(redeemable_programs=OuterRef("pk"))
        .values("redeemable_programs")
        .annotate(count=Count("pk"))
        .values("count")
    )
    Program.objects.filter(pk=program_id).update(
        redeemable_centers_count=Coalesce(Subquery(subquery), Value(0))
    )


def update_program_sessions_count(program_id: UUID) -> None:
    subquery = (
        ProgramService.objects.filter(program_id=OuterRef("pk"))
        .values("program_id")
        .annotate(total=Sum("sessions_count"))
        .values("total")
    )
    Program.objects.filter(pk=program_id).update(
        sessions_count=Coalesce(Subquery(subquery), Value(0))
    )


def cancel_program_services(
    program_id, cancelled_by=None, cancellation_reason=None
) -> None:
    ProgramService.objects.filter(program_id=program_id).update(
        is_active=False,
        cancelled_by=cancelled_by,
        cancellation_reason=cancellation_reason,
    )
