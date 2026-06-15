from uuid import UUID

from django.db import transaction
from django.db.models import F, Value, Subquery, OuterRef, Sum, Count
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.centers.models import Center
from programs.models import (
    Program,
    ProgramService,
    RedemptionHistory,
    TherapyProgram,
    TherapyProgramService,
)
from programs.utils.constants import RedemptionType


def increment_program_service_sessions_used(program_service_id) -> None:
    TherapyProgramService.objects.filter(program_service__pk=program_service_id).update(
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


def increment_service_cancelled_count(program_id, count: int = 1) -> None:
    Program.objects.filter(pk=program_id).update(
        services_cancelled=F("services_cancelled") + count
    )


def cancel_all_program_services(
    program_id,
    center_id,
    cancelled_by=None,
    cancellation_reason=None,
    cancelled_date=timezone.localdate(),
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
    program_service_id,
    program_id,
    center_id,
    cancelled_by=None,
    cancellation_reason=None,
    cancelled_date=timezone.localdate(),
) -> None:
    has_other_services = (
        ProgramService.objects.filter(program=program_id)
        .exclude(pk=program_service_id)
        .exists()
    )
    if not has_other_services:
        cancel_all_program_services(
            program_id, center_id, cancelled_by, cancellation_reason, cancelled_date
        )
        return None

    therapy_program_service = (
        TherapyProgramService.objects.filter(program_service__pk=program_service_id)
        .select_related("program_service")
        .first()
    )
    remaining = (
        therapy_program_service.sessions_count - therapy_program_service.sessions_used
    )
    center = Center.objects.filter(pk=center_id).first()

    sessions_cancelled_subquery = (
        TherapyProgramService.objects.filter(
            program_service__program=OuterRef("program")
        )
        .values("program_service__program")
        .annotate(total=Sum("sessions_cancelled"))
        .values("total")
    )

    with transaction.atomic():
        ProgramService.objects.filter(pk=program_service_id).update(
            is_active=False,
            cancelled_by=cancelled_by,
            cancelled_at=timezone.now(),
            cancellation_reason=cancellation_reason,
            cancelled_date=cancelled_date,
        )
        TherapyProgramService.objects.filter(
            program_service__pk=program_service_id
        ).update(sessions_cancelled=F("sessions_count") - F("sessions_used"))
        TherapyProgram.objects.filter(program=program_id).update(
            sessions_cancelled=Coalesce(
                Subquery(sessions_cancelled_subquery), Value(0)
            ),
        )
        increment_service_cancelled_count(program_id)
        RedemptionHistory.objects.create(
            therapy_program_service=therapy_program_service,
            redeem_center=center,
            redeemed_at=timezone.now(),
            quantity=remaining,
            redeemed_by=cancelled_by,
            redemption_type=RedemptionType.CANCEL,
            redeemed_date=cancelled_date,
        )
    return None
