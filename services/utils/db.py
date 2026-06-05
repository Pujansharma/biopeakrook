from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from services.models import Service, CenterServiceAssignment
from services.programs.models import Program, ProgramService, RedemptionHistory


def update_service_center_count(service_id: UUID) -> None:
    subquery = (
        CenterServiceAssignment.objects.filter(
            service_id=OuterRef("pk"), is_active=True
        )
        .values("service_id")
        .annotate(count=Count("center_id"))
        .values("count")
    )
    Service.objects.filter(pk=service_id).update(
        centers_count=Coalesce(Subquery(subquery), Value(0))
    )


def redeem_program_service(
        program_service_id: UUID, center_id: UUID, redeemed_by, quantity: int, redeemed_date=timezone.localdate()
) -> None:
    with transaction.atomic():
        ProgramService.objects.filter(pk=program_service_id).update(
            sessions_used=F("sessions_used") + quantity
        )
        Program.objects.filter(program_services__pk=program_service_id).update(
            sessions_used=F("sessions_used") + quantity
        )
        RedemptionHistory.objects.create(
            program_service_id=program_service_id,
            redeem_center_id=center_id,
            redeemed_at=timezone.now(),
            quantity=quantity,
            redeemed_by=redeemed_by,
            redeemed_date=redeemed_date
        )


def redeem_all_program_services(
        program_id: UUID, center_id: UUID, redeemed_by, redeemed_date=timezone.localdate()
) -> int:
    services = list(
        ProgramService.objects.filter(program_id=program_id, is_active=True)
        .exclude(sessions_used=F("sessions_count"))
        .values("pk", "sessions_count", "sessions_used")
    )
    if not services:
        return 0

    now = timezone.now()
    total_quantity = 0
    service_ids = []
    histories = []

    for service in services:
        remaining = service["sessions_count"] - service["sessions_used"]
        total_quantity += remaining
        service_ids.append(service["pk"])
        histories.append(
            RedemptionHistory(
                program_service_id=service["pk"],
                redeem_center_id=center_id,
                redeemed_at=now,
                quantity=remaining,
                redeemed_by=redeemed_by,
                redeemed_date=redeemed_date,
            )
        )

    with transaction.atomic():
        ProgramService.objects.filter(pk__in=service_ids).update(
            sessions_used=F("sessions_count")
        )
        Program.objects.filter(pk=program_id).update(
            sessions_used=F("sessions_used") + total_quantity
        )
        RedemptionHistory.objects.bulk_create(histories)

    return total_quantity
