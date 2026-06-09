from uuid import UUID

from django.db import transaction
from django.db.models import F, Value, Subquery, OuterRef, Sum, Count
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.centers.models import Center
from programs.models import Program, ProgramService, RedemptionHistory
from programs.utils.constants import RedemptionType


def increment_program_service_sessions_used(program_service_id) -> None:
    ProgramService.objects.filter(pk=program_service_id).update(
        sessions_used=F("sessions_used") + 1
    )
    Program.objects.filter(program_services__pk=program_service_id).update(
        sessions_used=F("sessions_used") + 1
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
        ProgramService.objects.filter(program_id=program_id, is_active=True).values(
            "pk", "sessions_count", "sessions_used"
        )
    )
    if not active_services:
        return None

    now = timezone.now()
    service_ids = []
    histories = []

    for service in active_services:
        remaining = service["sessions_count"] - service["sessions_used"]
        service_ids.append(service["pk"])
        if remaining > 0:
            histories.append(
                RedemptionHistory(
                    program_service_id=service["pk"],
                    redeem_center_id=center_id,
                    redeemed_at=now,
                    quantity=remaining,
                    redeemed_by=cancelled_by,
                    redemption_type=RedemptionType.CANCEL,
                    redeemed_date=cancelled_date,
                )
            )

    sessions_cancelled_subquery = (
        ProgramService.objects.filter(program_id=OuterRef("pk"))
        .values("program_id")
        .annotate(total=Sum("sessions_cancelled"))
        .values("total")
    )

    with transaction.atomic():
        ProgramService.objects.filter(pk__in=service_ids).update(
            is_active=False,
            sessions_cancelled=F("sessions_count") - F("sessions_used"),
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
            cancelled_at=now,
            cancelled_date=cancelled_date,
        )
        Program.objects.filter(pk=program_id).update(
            sessions_cancelled=Coalesce(
                Subquery(sessions_cancelled_subquery), Value(0)
            ),
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
            cancelled_at=now,
            cancelled_date=cancelled_date,
        )
        increment_service_cancelled_count(program_id, count=len(active_services))
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
        ProgramService.objects.filter(program_id=program_id)
        .exclude(pk=program_service_id)
        .exists()
    )
    if not has_other_services:
        cancel_all_program_services(
            program_id, center_id, cancelled_by, cancellation_reason, cancelled_date
        )
        return None

    service_data = (
        ProgramService.objects.filter(pk=program_service_id)
        .values("sessions_count", "sessions_used")
        .first()
    )
    remaining = service_data["sessions_count"] - service_data["sessions_used"]

    sessions_cancelled_subquery = (
        ProgramService.objects.filter(program_id=OuterRef("pk"))
        .values("program_id")
        .annotate(total=Sum("sessions_cancelled"))
        .values("total")
    )

    with transaction.atomic():
        ProgramService.objects.filter(pk=program_service_id).update(
            is_active=False,
            cancelled_by=cancelled_by,
            cancelled_at=timezone.now(),
            cancellation_reason=cancellation_reason,
            sessions_cancelled=F("sessions_count") - F("sessions_used"),
            cancelled_date=cancelled_date,
        )
        Program.objects.filter(pk=program_id).update(
            sessions_cancelled=Coalesce(
                Subquery(sessions_cancelled_subquery), Value(0)
            ),
        )
        increment_service_cancelled_count(program_id)
        RedemptionHistory.objects.create(
            program_service_id=program_service_id,
            redeem_center_id=center_id,
            redeemed_at=timezone.now(),
            quantity=remaining,
            redeemed_by=cancelled_by,
            redemption_type=RedemptionType.CANCEL,
            redeemed_date=cancelled_date,
        )
    return None
