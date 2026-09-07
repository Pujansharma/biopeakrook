from django.core.exceptions import ValidationError

from appointments.models import Appointment, AppointmentAssociate
from appointments.utils.constants import AppointmentStatus

ALLOWED_TRANSITIONS = {
    "check-in": {AppointmentStatus.CONFIRMED},
    "start": {AppointmentStatus.CHECKED_IN},
    "mark-late": {AppointmentStatus.IN_PROGRESS},
    "complete": {AppointmentStatus.IN_PROGRESS},
    "cancel": {AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN},
    "no-show": {AppointmentStatus.CONFIRMED},
    "reschedule": {AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN},
}

TARGET_STATUS_BY_ACTION = {
    "check-in": AppointmentStatus.CHECKED_IN,
    "start": AppointmentStatus.IN_PROGRESS,
    "mark-late": AppointmentStatus.IN_PROGRESS,
    "complete": AppointmentStatus.COMPLETED,
    "cancel": AppointmentStatus.CANCELLED,
    "no-show": AppointmentStatus.NO_SHOW,
    "reschedule": AppointmentStatus.CONFIRMED,
}


def validate_transition(current_status, action):
    allowed_from_statuses = ALLOWED_TRANSITIONS.get(action)
    if allowed_from_statuses is None:
        raise ValidationError(f"Unknown appointment action: {action}")
    if current_status not in allowed_from_statuses:
        raise ValidationError(
            f"Cannot perform '{action}' from status '{current_status}'."
        )


def apply_status_change(appointment, action):
    validate_transition(appointment.status, action)
    target_status = TARGET_STATUS_BY_ACTION[action]
    appointment.status = target_status
    appointment.save(update_fields=["status", "updated_at"])
    sync_associate_status_snapshots(appointment)
    return appointment


def sync_associate_status_snapshots(appointment):
    AppointmentAssociate.objects.filter(appointment=appointment).update(
        appointment_status=appointment.status
    )
