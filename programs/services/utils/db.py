from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from appointments.utils.redemption import increment_therapy_sessions_used
from programs.models import (
    RedemptionHistory,
    TherapyProgram,
    TherapyProgramService,
)
from programs.services.models import (
    Service,
    CenterServiceAssignment,
    ServiceProductAssignment,
)


def update_service_center_count(service_id: UUID) -> None:
    subquery = (
        CenterServiceAssignment.objects.filter(
            service=OuterRef("pk"), is_active=True
        )
        .values("service")
        .annotate(count=Count("center"))
        .values("count")
    )
    Service.objects.filter(pk=service_id).update(
        centers_count=Coalesce(Subquery(subquery), Value(0))
    )


def update_service_product_count(service_id: UUID) -> None:
    subquery = (
        ServiceProductAssignment.objects.filter(
            service=OuterRef("pk"),
            is_active=True,
        )
        .values("service")
        .annotate(count=Count("product"))
        .values("count")
    )
    Service.objects.filter(pk=service_id).update(
        products_count=Coalesce(Subquery(subquery), Value(0))
    )


def redeem_program_service(
    program_service_id: UUID,
    center_id: UUID,
    redeemed_by,
    quantity: int,
    redeemed_date=timezone.localdate(),
) -> None:
    center = Center.objects.filter(pk=center_id).first()
    therapy_program_service = TherapyProgramService.objects.filter(
        program_service__pk=program_service_id
    ).first()
    with transaction.atomic():
        burned = increment_therapy_sessions_used(program_service_id, quantity)
        if burned != 1:
            raise serializers.ValidationError(
                "No sessions remaining for this service."
            )
        RedemptionHistory.objects.create(
            therapy_program_service=therapy_program_service,
            redeem_center=center,
            redeemed_at=timezone.now(),
            quantity=quantity,
            redeemed_by=redeemed_by,
            redeemed_date=redeemed_date,
        )


def redeem_all_program_services(
    program_id: UUID,
    center_id: UUID,
    redeemed_by,
    redeemed_date=timezone.localdate(),
) -> int:
    services = list(
        TherapyProgramService.objects.filter(
            program_service__program=program_id,
            program_service__is_active=True,
        )
        .exclude(sessions_used=F("sessions_count"))
        .select_related("program_service")
    )
    if not services:
        return 0

    now = timezone.now()
    center = Center.objects.filter(pk=center_id).first()
    total_quantity = 0
    histories = []

    for therapy_program_service in services:
        remaining = (
            therapy_program_service.sessions_count
            - therapy_program_service.sessions_used
        )
        total_quantity += remaining
        histories.append(
            RedemptionHistory(
                therapy_program_service=therapy_program_service,
                redeem_center=center,
                redeemed_at=now,
                quantity=remaining,
                redeemed_by=redeemed_by,
                redeemed_date=redeemed_date,
            )
        )

    with transaction.atomic():
        therapy_program_service_identifiers = [
            therapy_program_service.pk for therapy_program_service in services
        ]
        TherapyProgramService.objects.filter(
            pk__in=therapy_program_service_identifiers
        ).update(
            sessions_used=F("sessions_count")
        )
        TherapyProgram.objects.filter(program=program_id).update(
            sessions_used=F("sessions_used") + total_quantity
        )
        RedemptionHistory.objects.bulk_create(histories)

    return total_quantity
