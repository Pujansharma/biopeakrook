from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, OuterRef, Subquery
from django.utils import timezone

from services.models import Service
from services.programs.models import Program, ProgramService, RedemptionHistory


def update_service_center_count(service_id: UUID) -> None:
    subquery = (
        Service.centers.through.objects.filter(service_id=OuterRef("pk"))
        .values("service_id")
        .annotate(cnt=Count("center_id"))
        .values("cnt")
    )
    Service.objects.filter(pk=service_id).update(centers_count=Subquery(subquery))


def redeem_program_service(
    program_service_id: UUID, center_id: UUID, redeemed_by, quantity: int
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
        )
