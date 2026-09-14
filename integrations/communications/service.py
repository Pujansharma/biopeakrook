from functools import partial

from django.db import transaction

from appointments.models import Appointment
from integrations.communications.outbox import enqueue_appointment_message
from integrations.utils.constants import CommunicationEventType


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


queue_appointment_confirmed = send_appointment_confirmed
queue_appointment_cancelled = send_appointment_cancelled
queue_appointment_rescheduled = send_appointment_rescheduled
