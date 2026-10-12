from datetime import timedelta
from functools import partial

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from appointments.models import Appointment, AssociateAvailabilityBlock, AssociateLeave
from appointments.utils.constants import AppointmentStatus, AvailabilityOrigin
from integrations.communications.outbox import (
    enqueue_appointment_message,
    enqueue_associate_block_sync,
    enqueue_associate_leave_sync,
    enqueue_whatsapp_only_message,
)
from integrations.communications.wake import publish_outbox_wake
from integrations.models import CommunicationOutbox
from integrations.utils.constants import (
    CommunicationChannel,
    CommunicationEventType,
    CommunicationOutboxStatus,
)

REMINDER_LEAD = timedelta(hours=1)
# Match process_communication_outbox default --limit so one sweep drains what it enqueues.
REMINDER_ENQUEUE_LIMIT = 50


def send_appointment_confirmed(appointment):
    return enqueue_appointment_message(
        appointment,
        CommunicationEventType.APPOINTMENT_CONFIRMED,
    )


def send_appointment_cancelled(appointment):
    return enqueue_appointment_message(
        appointment,
        CommunicationEventType.APPOINTMENT_CANCELLED,
    )


def send_appointment_rescheduled(appointment, *, previous_start_datetime=None):
    return enqueue_appointment_message(
        appointment,
        CommunicationEventType.APPOINTMENT_RESCHEDULED,
        previous_start_datetime=previous_start_datetime,
    )


def send_appointment_no_show(appointment):
    return enqueue_whatsapp_only_message(
        appointment,
        CommunicationEventType.APPOINTMENT_NO_SHOW,
        wake=True,
    )


def load_appointment_for_outbox(appointment_id):
    return (
        Appointment.objects.select_related(
            "customer_profile__customer__user",
            "service",
            "center",
        )
        .filter(pk=appointment_id)
        .first()
    )


def queue_confirmed_by_appointment_id(appointment_id):
    appointment = load_appointment_for_outbox(appointment_id)
    if appointment is None:
        return None
    return send_appointment_confirmed(appointment)


def queue_cancelled_by_appointment_id(appointment_id):
    appointment = load_appointment_for_outbox(appointment_id)
    if appointment is None:
        return None
    return send_appointment_cancelled(appointment)


def queue_rescheduled_by_appointment_id(appointment_id, previous_start_datetime):
    appointment = load_appointment_for_outbox(appointment_id)
    if appointment is None:
        return None
    return send_appointment_rescheduled(
        appointment,
        previous_start_datetime=previous_start_datetime,
    )


def queue_no_show_by_appointment_id(appointment_id):
    appointment = load_appointment_for_outbox(appointment_id)
    if appointment is None:
        return None
    return send_appointment_no_show(appointment)


def schedule_queue_appointment_confirmed(appointment):
    transaction.on_commit(
        partial(queue_confirmed_by_appointment_id, appointment.pk)
    )


def schedule_queue_appointment_cancelled(appointment):
    transaction.on_commit(
        partial(queue_cancelled_by_appointment_id, appointment.pk)
    )


def schedule_queue_appointment_rescheduled(appointment, *, previous_start_datetime):
    transaction.on_commit(
        partial(
            queue_rescheduled_by_appointment_id,
            appointment.pk,
            previous_start_datetime,
        )
    )


def schedule_queue_appointment_no_show(appointment):
    transaction.on_commit(
        partial(queue_no_show_by_appointment_id, appointment.pk)
    )


def due_reminder_appointments(*, now=None, limit: int = REMINDER_ENQUEUE_LIMIT):
    """
    Confirmed appointments starting within the next hour with no WhatsApp
    reminder outbox row yet (any status — once enqueued, never again).
    """
    if now is None:
        now = timezone.now()
    window_end = now + REMINDER_LEAD
    existing_reminder = CommunicationOutbox.objects.filter(
        appointment_id=OuterRef("pk"),
        channel=CommunicationChannel.WHATSAPP,
        event_type=CommunicationEventType.APPOINTMENT_REMINDER,
    )
    return (
        Appointment.objects.select_related(
            "customer_profile__customer__user",
            "service",
            "center",
        )
        .filter(
            status=AppointmentStatus.CONFIRMED,
            start_datetime__gt=now,
            start_datetime__lte=window_end,
        )
        .exclude(Exists(existing_reminder))
        .order_by("start_datetime")[:limit]
    )


def enqueue_due_appointment_reminders(*, limit: int = REMINDER_ENQUEUE_LIMIT) -> list:
    """
    Create WhatsApp reminder outbox rows for due appointments.
    No SQS wake — sweep drains outbox in the same job.
    """
    return [
        enqueue_whatsapp_only_message(
            appointment,
            CommunicationEventType.APPOINTMENT_REMINDER,
            wake=False,
        )
        for appointment in due_reminder_appointments(limit=limit)
    ]


def _wake_if_pending(message):
    if message is None:
        return message
    if message.status in {
        CommunicationOutboxStatus.PENDING,
        CommunicationOutboxStatus.FAILED,
    }:
        publish_outbox_wake()
    return message


def queue_associate_block_sync(*, block_id=None, series_id=None):
    if series_id is not None:
        block = (
            AssociateAvailabilityBlock.objects.filter(series_id=series_id)
            .order_by("pk")
            .first()
        )
        if block is None or block.origin != AvailabilityOrigin.MANUAL:
            return None
        return _wake_if_pending(enqueue_associate_block_sync(series_id=series_id))

    block = AssociateAvailabilityBlock.objects.filter(pk=block_id).first()
    if block is None or block.origin != AvailabilityOrigin.MANUAL:
        return None
    if block.series_id is not None:
        return _wake_if_pending(
            enqueue_associate_block_sync(series_id=block.series_id)
        )
    return _wake_if_pending(enqueue_associate_block_sync(block=block))


def queue_associate_leave_sync(leave_id):
    leave = AssociateLeave.objects.filter(pk=leave_id).first()
    if leave is None or leave.origin != AvailabilityOrigin.MANUAL:
        return None
    return _wake_if_pending(enqueue_associate_leave_sync(leave))


def schedule_queue_associate_block_sync(*, block=None, series_id=None):
    transaction.on_commit(
        partial(
            queue_associate_block_sync,
            block_id=None if block is None else block.pk,
            series_id=series_id,
        )
    )


def schedule_queue_associate_leave_sync(leave):
    transaction.on_commit(partial(queue_associate_leave_sync, leave.pk))


queue_appointment_confirmed = send_appointment_confirmed
queue_appointment_cancelled = send_appointment_cancelled
queue_appointment_rescheduled = send_appointment_rescheduled
queue_appointment_no_show = send_appointment_no_show
