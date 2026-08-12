from datetime import date
from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.centers.models import Center
from accounts.utils import get_user_model
from programs.models import (
    Program,
    ProgramService,
    RedemptionHistory,
    TherapyProgram,
    TherapyProgramService,
)
from programs.services.utils.constants import ServiceCategory
from programs.utils.constants import ProgramType, RedemptionType

User = get_user_model()


def increment_program_service_sessions_used(program_service_id: UUID) -> None:
    TherapyProgramService.objects.filter(
        program_service__pk=program_service_id
    ).update(
        sessions_used=F("sessions_used") + 1
    )
    TherapyProgram.objects.filter(
        program__program_services__pk=program_service_id
    ).update(sessions_used=F("sessions_used") + 1)


def update_program_services_count(program_id: UUID) -> None:
    subquery = (
        ProgramService.objects.filter(program=OuterRef("pk"))
        .values("program")
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
        TherapyProgramService.objects.filter(
            program_service__program=OuterRef("program")
        )
        .values("program_service__program")
        .annotate(total=Sum("sessions_count"))
        .values("total")
    )
    TherapyProgram.objects.filter(program=program_id).update(
        sessions_count=Coalesce(Subquery(subquery), Value(0))
    )


def increment_service_cancelled_count(program_id: UUID, count: int = 1) -> None:
    Program.objects.filter(pk=program_id).update(
        services_cancelled=F("services_cancelled") + count
    )


def cancel_all_program_services(
        program_id: UUID,
        center_id: UUID,
        cancelled_by: User | None = None,
        cancellation_reason: str | None = None,
        cancelled_date: date = timezone.localdate(),
) -> None:
    active_services = list(
        TherapyProgramService.objects.filter(
            program_service__program=program_id, program_service__is_active=True
        ).select_related("program_service")
    )
    if not active_services:
        return None

    now = timezone.now()
    center = Center.objects.filter(pk=center_id).first()
    if not center:
        return None

    program_service_ids = []
    histories = []

    for therapy_program_service in active_services:
        remaining = (
                therapy_program_service.sessions_count
                - therapy_program_service.sessions_used
        )
        program_service_ids.append(therapy_program_service.program_service.pk)
        if remaining > 0:
            histories.append(
                RedemptionHistory(
                    therapy_program_service=therapy_program_service,
                    redeem_center=center,
                    redeemed_at=now,
                    quantity=remaining,
                    redeemed_by=cancelled_by,
                    redemption_type=RedemptionType.CANCEL,
                    redeemed_date=cancelled_date,
                )
            )

    sessions_cancelled_subquery = (
        TherapyProgramService.objects.filter(
            program_service__program=OuterRef("program")
        )
        .values("program_service__program")
        .annotate(total=Sum("sessions_cancelled"))
        .values("total")
    )

    with transaction.atomic():
        ProgramService.objects.filter(pk__in=program_service_ids).update(
            is_active=False,
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
            cancelled_at=now,
            cancelled_date=cancelled_date,
        )
        TherapyProgramService.objects.filter(
            program_service__pk__in=program_service_ids
        ).update(
            sessions_cancelled=F("sessions_count") - F("sessions_used"),
        )
        TherapyProgram.objects.filter(program=program_id).update(
            sessions_cancelled=Coalesce(
                Subquery(sessions_cancelled_subquery), Value(0)
            ),
        )
        Program.objects.filter(pk=program_id).update(
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
            cancelled_at=now,
            cancelled_date=cancelled_date,
        )
        increment_service_cancelled_count(program_id, count=len(program_service_ids))
        RedemptionHistory.objects.bulk_create(histories)
    return None


def cancel_program_service(
        program_service_id: UUID,
        program_id: UUID,
        center_id: UUID | None = None,
        cancelled_by: User | None = None,
        cancellation_reason: str | None = None,
        cancelled_date: date = timezone.localdate(),
) -> None:
    program_service = (
        ProgramService.objects.filter(
            pk=program_service_id,
            program__pk=program_id,
        )
        .select_related(
            "program",
            "service",
        )
        .first()
    )
    if not program_service:
        return None

    has_other_services = (
        ProgramService.objects.filter(program=program_id)
        .exclude(pk=program_service_id)
        .exists()
    )
    is_therapy_service = (
        program_service.service.service_category == ServiceCategory.THERAPY
    )
    if is_therapy_service and not center_id:
        return None
    if is_therapy_service and not has_other_services:
        cancel_all_program_services(
            program_id, center_id, cancelled_by, cancellation_reason, cancelled_date
        )
        return None

    therapy_program_service = None
    center = None
    remaining = 0
    if is_therapy_service:
        therapy_program_service = (
            TherapyProgramService.objects.filter(
                program_service__pk=program_service_id
            )
            .select_related("program_service")
            .first()
        )
        center = Center.objects.filter(pk=center_id).first()
        if not therapy_program_service or not center:
            return None
        remaining = (
                therapy_program_service.sessions_count
                - therapy_program_service.sessions_used
        )

    now = timezone.now()

    with transaction.atomic():
        ProgramService.objects.filter(pk=program_service_id).update(
            is_active=False,
            cancelled_by=cancelled_by,
            cancelled_at=now,
            cancellation_reason=cancellation_reason,
            cancelled_date=cancelled_date,
        )
        increment_service_cancelled_count(program_id)
        if not has_other_services:
            Program.objects.filter(pk=program_id).update(
                cancelled_by=cancelled_by,
                cancellation_reason=cancellation_reason,
                cancelled_at=now,
                cancelled_date=cancelled_date,
            )
        if is_therapy_service:
            sessions_cancelled_subquery = (
                TherapyProgramService.objects.filter(
                    program_service__program=OuterRef("program")
                )
                .values("program_service__program")
                .annotate(total=Sum("sessions_cancelled"))
                .values("total")
            )
            TherapyProgramService.objects.filter(
                program_service__pk=program_service_id
            ).update(
                sessions_cancelled=F("sessions_count") - F("sessions_used")
            )
            TherapyProgram.objects.filter(program=program_id).update(
                sessions_cancelled=Coalesce(
                    Subquery(sessions_cancelled_subquery), Value(0)
                ),
            )
        if (
            is_therapy_service
            and program_service.program.program_type == ProgramType.THERAPY
        ):
            RedemptionHistory.objects.create(
                therapy_program_service=therapy_program_service,
                redeem_center=center,
                redeemed_at=now,
                quantity=remaining,
                redeemed_by=cancelled_by,
                redemption_type=RedemptionType.CANCEL,
                redeemed_date=cancelled_date,
            )
    return None
