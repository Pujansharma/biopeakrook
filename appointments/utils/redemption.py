from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework import serializers

from appointments.models import Appointment, AppointmentAuditLog
from appointments.utils.calendar import center_local_date
from appointments.utils.constants import (
    AppointmentAuditAction,
    AppointmentStatus,
    BUSY_APPOINTMENT_STATUSES,
)
from appointments.utils.operations import invalidate_operations_cache
from appointments.utils.transitions import sync_associate_status_snapshots
from programs.models import (
    RedemptionHistory,
    TherapyProgram,
    TherapyProgramService,
)
from programs.utils.constants import ProgramType, RedemptionType

OPEN_APPOINTMENT_STATUSES = tuple(BUSY_APPOINTMENT_STATUSES)
OPEN_APPOINTMENT_EXISTS_MESSAGE = (
    "An open appointment already exists for this program service."
)
SESSIONS_REMAINING_MESSAGE = "No sessions remaining for this service."


def program_expiry_before_appointment_message(expires_at):
    expires_on = f"{expires_at.day} {expires_at.strftime('%b %Y')}"
    return (
        f"This package expires on {expires_on}. "
        "Please choose a date on or before it."
    )


def ensure_program_covers_appointment_date(
    program,
    appointment_date,
    field_name="program_service_id",
):
    """Reject when appointment_date is after program.expires_at (null expiry = open-ended)."""
    expires_at = program.expires_at
    if expires_at is not None and appointment_date > expires_at:
        raise serializers.ValidationError(
            {field_name: [program_expiry_before_appointment_message(expires_at)]}
        )


def therapy_sessions_remaining(therapy_program_service):
    if therapy_program_service.sessions_count == 0:
        return None
    return (
        therapy_program_service.sessions_count
        - therapy_program_service.sessions_used
    )


def has_remaining_therapy_sessions(therapy_program_service):
    remaining = therapy_sessions_remaining(therapy_program_service)
    if remaining is None:
        return True
    return remaining > 0


def get_open_appointment_for_program_service(program_service_id):
    return (
        Appointment.objects.filter(
            program_service__pk=program_service_id,
            status__in=OPEN_APPOINTMENT_STATUSES,
        )
        .select_related("center", "room", "program_service")
        .first()
    )


def resolve_bookable_therapy_program_service(
    program_service_id,
    customer_profile,
    service,
    center,
    appointment_date,
):
    therapy_program_service = (
        TherapyProgramService.objects.filter(
            program_service__pk=program_service_id,
            program_service__program__customer_profile=customer_profile,
            program_service__service=service,
            program_service__is_active=True,
            program_service__program__program_type=ProgramType.THERAPY,
            program_service__program__is_active=True,
        )
        .select_related(
            "program_service",
            "program_service__program",
            "program_service__service",
        )
        .first()
    )
    if therapy_program_service is None:
        raise serializers.ValidationError(
            {
                "program_service_id": [
                    "Invalid therapy program service for this customer and service."
                ]
            }
        )

    program = therapy_program_service.program_service.program
    ensure_program_covers_appointment_date(
        program,
        appointment_date,
        field_name="program_service_id",
    )

    redeemable_at_center = program.redeemable_centers.filter(pk=center.pk).exists()
    if not redeemable_at_center and program.center.pk != center.pk:
        raise serializers.ValidationError(
            {
                "program_service_id": [
                    "This program service is not redeemable at this center."
                ]
            }
        )

    if get_open_appointment_for_program_service(program_service_id) is not None:
        raise serializers.ValidationError(
            {"program_service_id": [OPEN_APPOINTMENT_EXISTS_MESSAGE]}
        )

    if not has_remaining_therapy_sessions(therapy_program_service):
        raise serializers.ValidationError(
            {"program_service_id": [SESSIONS_REMAINING_MESSAGE]}
        )

    return therapy_program_service


def therapy_program_services_for_customer_service(
    customer_profile,
    service,
    program_service_id=None,
):
    queryset = TherapyProgramService.objects.filter(
        program_service__program__customer_profile=customer_profile,
        program_service__service=service,
        program_service__is_active=True,
        program_service__program__program_type=ProgramType.THERAPY,
        program_service__program__is_active=True,
    ).select_related("program_service__program")
    if program_service_id is not None:
        queryset = queryset.filter(program_service__pk=program_service_id)
    return queryset


def ensure_customer_slot_within_therapy_programs(
    customer_profile,
    service,
    slot_date,
    program_service_id=None,
):
    """
    Slots: appointment day must fall on/before package expiry.

    With program_service_id → that line only.
    Without → block only when every matching active therapy line expires before slot_date.
    """
    queryset = therapy_program_services_for_customer_service(
        customer_profile,
        service,
        program_service_id=program_service_id,
    )
    if program_service_id is not None:
        therapy_program_service = queryset.first()
        if therapy_program_service is None:
            raise serializers.ValidationError(
                {
                    "program_service_id": [
                        "Invalid therapy program service for this customer and service."
                    ]
                }
            )
        ensure_program_covers_appointment_date(
            therapy_program_service.program_service.program,
            slot_date,
            field_name="date",
        )
        return

    if not queryset.exists():
        return
    covers_slot = Q(program_service__program__expires_at__isnull=True) | Q(
        program_service__program__expires_at__gte=slot_date
    )
    if queryset.filter(covers_slot).exists():
        return
    earliest = (
        queryset.exclude(program_service__program__expires_at__isnull=True)
        .order_by("program_service__program__expires_at")
        .select_related("program_service__program")
        .first()
    )
    raise serializers.ValidationError(
        {
            "date": [
                program_expiry_before_appointment_message(
                    earliest.program_service.program.expires_at
                )
            ]
        }
    )


def schedule_appointment_redemption(appointment, redeemed_by):
    if appointment.program_service is None:
        return None

    program_service_pk = appointment.program_service.pk
    therapy_program_service = TherapyProgramService.objects.filter(
        program_service__pk=program_service_pk
    ).first()
    if therapy_program_service is None:
        return None

    return RedemptionHistory.objects.create(
        therapy_program_service=therapy_program_service,
        redeem_center=appointment.center,
        appointment=appointment,
        redeemed_at=timezone.localtime(),
        redeemed_date=timezone.localdate(),
        quantity=1,
        redeemed_by=redeemed_by,
        redemption_type=RedemptionType.SCHEDULED,
    )


def increment_therapy_sessions_used(program_service_id, quantity):
    """Burn sessions; no-op when finite and would exceed remaining. Returns TPS rows updated."""
    updated = (
        TherapyProgramService.objects.filter(program_service__pk=program_service_id)
        .filter(
            Q(sessions_count=0)
            | Q(sessions_used__lte=F("sessions_count") - quantity)
        )
        .update(sessions_used=F("sessions_used") + quantity)
    )
    if updated != 1:
        return 0
    TherapyProgram.objects.filter(
        program__program_services__pk=program_service_id
    ).update(sessions_used=F("sessions_used") + quantity)
    return updated


def burn_therapy_sessions_or_raise(program_service_pk, quantity):
    burned = increment_therapy_sessions_used(program_service_pk, quantity)
    if burned != 1:
        raise serializers.ValidationError(SESSIONS_REMAINING_MESSAGE)


def claim_scheduled_redemption_and_burn(history, appointment, redeemed_by):
    """Flip SCHEDULED→REDEEM then burn only if this caller won the claim."""
    quantity = history.quantity
    now = timezone.localtime()
    updated = RedemptionHistory.objects.filter(
        pk=history.pk,
        redemption_type=RedemptionType.SCHEDULED,
    ).update(
        redemption_type=RedemptionType.REDEEM,
        redeemed_at=now,
        redeemed_date=timezone.localdate(),
        redeemed_by=redeemed_by,
    )
    if updated != 1:
        history.refresh_from_db()
        return history
    burn_therapy_sessions_or_raise(appointment.program_service.pk, quantity)
    history.refresh_from_db()
    return history


def create_missing_redeem_history_and_burn(appointment, redeemed_by):
    """Create REDEEM history then burn; on OneToOne race, claim or no-op."""
    program_service_pk = appointment.program_service.pk
    therapy_program_service = TherapyProgramService.objects.filter(
        program_service__pk=program_service_pk
    ).first()
    if therapy_program_service is None:
        return None

    now = timezone.localtime()
    try:
        with transaction.atomic():
            history = RedemptionHistory.objects.create(
                therapy_program_service=therapy_program_service,
                redeem_center=appointment.center,
                appointment=appointment,
                redeemed_at=now,
                redeemed_date=timezone.localdate(),
                quantity=1,
                redeemed_by=redeemed_by,
                redemption_type=RedemptionType.REDEEM,
            )
    except IntegrityError:
        history = RedemptionHistory.objects.filter(appointment=appointment).first()
        if history is None:
            return None
        if history.redemption_type == RedemptionType.REDEEM:
            return history
        if history.redemption_type != RedemptionType.SCHEDULED:
            return history
        return claim_scheduled_redemption_and_burn(
            history, appointment, redeemed_by
        )

    burn_therapy_sessions_or_raise(program_service_pk, 1)
    return history


def complete_appointment_redemption(appointment, redeemed_by):
    """Burn scheduled redemption. Expiry gated by callers before status flip."""
    if appointment.program_service is None:
        return None

    with transaction.atomic():
        history = RedemptionHistory.objects.filter(appointment=appointment).first()
        if history is None:
            return create_missing_redeem_history_and_burn(appointment, redeemed_by)
        if history.redemption_type == RedemptionType.REDEEM:
            return history
        if history.redemption_type != RedemptionType.SCHEDULED:
            return history
        return claim_scheduled_redemption_and_burn(
            history, appointment, redeemed_by
        )


def cancel_appointment_redemption(appointment, redeemed_by):
    with transaction.atomic():
        history = RedemptionHistory.objects.filter(appointment=appointment).first()
        if history is None:
            return None
        if history.redemption_type != RedemptionType.SCHEDULED:
            return history

        now = timezone.localtime()
        updated = RedemptionHistory.objects.filter(
            pk=history.pk,
            redemption_type=RedemptionType.SCHEDULED,
        ).update(
            redemption_type=RedemptionType.CANCELLED,
            redeemed_at=now,
            redeemed_date=timezone.localdate(),
            redeemed_by=redeemed_by,
        )
        if updated != 1:
            history.refresh_from_db()
            return history
        history.refresh_from_db()
        return history


def force_complete_appointment(appointment, actor):
    """Claim open→COMPLETED; return None if another writer already closed it."""
    if appointment.program_service is not None:
        ensure_program_covers_appointment_date(
            appointment.program_service.program,
            center_local_date(appointment.center, appointment.start_datetime),
            field_name="program_service_id",
        )
    updated = Appointment.objects.filter(
        pk=appointment.pk,
        status__in=OPEN_APPOINTMENT_STATUSES,
    ).update(
        status=AppointmentStatus.COMPLETED,
        updated_at=timezone.localtime(),
    )
    if updated != 1:
        return None
    appointment.refresh_from_db()
    sync_associate_status_snapshots(appointment)
    AppointmentAuditLog.objects.create(
        appointment=appointment,
        actor=actor,
        action=AppointmentAuditAction.COMPLETE,
        note="Completed via QR redemption.",
    )
    complete_appointment_redemption(appointment, actor)
    invalidate_operations_cache(appointment.center.pk)
    return appointment


def complete_open_appointment_for_program_service(
    program_service_id,
    redeemed_by,
):
    appointment = get_open_appointment_for_program_service(program_service_id)
    if appointment is None:
        return None
    with transaction.atomic():
        return force_complete_appointment(appointment, redeemed_by)


def appointment_has_redeem_history(appointment_id):
    return RedemptionHistory.objects.filter(
        appointment__pk=appointment_id,
        redemption_type=RedemptionType.REDEEM,
    ).exists()


def try_complete_open_appointment_for_single_redeem(program_service_id, redeemed_by):
    """
    QR SINGLE with open apt: complete+burn, or idempotent success if already done.

    Returns (outcome, appointment):
      completed — open apt completed (or already completed+REDEEM); do not classic redeem
      no_open — no open apt; caller may classic redeem
      failed — open apt was observed but not completable (e.g. cancelled); do not classic redeem
    """
    open_appointment = get_open_appointment_for_program_service(program_service_id)
    if open_appointment is None:
        return ("no_open", None)

    observed_appointment_id = open_appointment.pk
    completed_appointment = complete_open_appointment_for_program_service(
        program_service_id,
        redeemed_by,
    )
    if completed_appointment is not None:
        return ("completed", completed_appointment)

    observed = Appointment.objects.filter(pk=observed_appointment_id).first()
    if (
        observed is not None
        and observed.status == AppointmentStatus.COMPLETED
        and appointment_has_redeem_history(observed_appointment_id)
    ):
        return ("completed", observed)

    return ("failed", None)
