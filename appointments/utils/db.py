from collections import defaultdict

from django.utils import timezone

from appointments.models import Appointment, AppointmentHistory, Schedule
from appointments.utils.constants import AppointmentStatus


def create_appointment(specialist, participant, start_dt, end_dt, created_by=None):
    """Helper to create appointment with validation."""
    # Validate slot is available
    # Create appointment with status=pending
    return Appointment.objects.create(...)


def confirm_appointment(appointment, confirmed_by=None):
    """Helper to confirm appointment."""

    Appointment.objects.filter(pk=appointment.pk).update(
        status=AppointmentStatus.CONFIRMED,
        confirmed_at=timezone.localtime(),
        confirmed_by=confirmed_by,
    )
    appointment.refresh_from_db()
    return appointment


def cancel_appointment(appointment, reason, cancelled_by=None):
    """Helper to cancel appointment."""

    Appointment.objects.filter(pk=appointment.pk).update(
        status=AppointmentStatus.CANCELLED,
        cancellation_reason=reason,
        cancelled_at=timezone.localtime(),
        cancelled_by=cancelled_by,
    )
    appointment.refresh_from_db()
    return appointment


def complete_appointment(appointment):
    """Helper to mark appointment as completed."""
    Appointment.objects.filter(pk=appointment.pk).update(
        status=AppointmentStatus.COMPLETED,
        completed_at=timezone.localtime()
    )
    appointment.refresh_from_db()
    return appointment


# When rescheduling:
def reschedule_appointment(
        appointment, start_datetime, end_datetime, reason, user
):
    """Helper to reschedule appointment."""
    # 1. Save old values to history
    AppointmentHistory.objects.create(
        appointment=appointment,
        start_datetime=appointment.start_datetime,  # OLD
        end_datetime=appointment.end_datetime,  # OLD
        reason=reason,
        rescheduled_by=user
    )

    # 2. Update appointment with new times
    appointment.start_datetime = start_datetime
    appointment.end_datetime = end_datetime
    appointment.save(update_fields=[
        'start_datetime', 'end_datetime'
    ])

    return appointment


def get_schedules_for_associate(associate, center=None):
    """
    Fetch schedules from the DB and return them grouped by day_of_week.

    Returns:
        dict[str, list[Schedule]]: e.g. {'0': [schedule1, schedule2], '1': [...]}
        Keys are day_of_week strings ('0'=Monday .. '6'=Sunday).
    """
    qs = Schedule.objects.filter(associate=associate)
    if center is not None:
        qs = qs.filter(center=center)

    grouped = defaultdict(list)
    for schedule in qs:
        grouped[schedule.day_of_week].append(schedule)

    return dict(grouped)
