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


queue_appointment_confirmed = send_appointment_confirmed
queue_appointment_cancelled = send_appointment_cancelled
queue_appointment_rescheduled = send_appointment_rescheduled
