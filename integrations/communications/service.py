from functools import partial

from django.db import transaction

from appointments.models import Appointment, AssociateAvailabilityBlock, AssociateLeave
from appointments.utils.constants import AvailabilityOrigin
from integrations.communications.outbox import (
    enqueue_appointment_message,
    enqueue_associate_block_sync,
    enqueue_associate_leave_sync,
)
from integrations.communications.wake import publish_outbox_wake
from integrations.utils.constants import (
    CommunicationEventType,
    CommunicationOutboxStatus,
)


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
