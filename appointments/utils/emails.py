import html

from django.utils import timezone

from appointments.models import Appointment
from core.utils.constants import AppointmentModes

APPOINTMENT_DATE_FORMAT = "%d %b %Y"
APPOINTMENT_TIME_FORMAT = "%I:%M %p"


def get_center_clinic_address(center) -> str:
    return center.full_address


def build_location_note(appointment: Appointment) -> str:
    if appointment.modality == AppointmentModes.VIRTUAL:
        return "This is a virtual appointment. Join using the Google Meet link on the calendar invite.\n\n"
    clinic_address = html.escape(get_center_clinic_address(appointment.center))
    return f"<b>Clinic Address:</b> {clinic_address}\n\n"


def build_attendance_note(appointment: Appointment) -> str:
    if appointment.modality == AppointmentModes.VIRTUAL:
        return "<b>Note:</b> Please join the meeting on time."
    return "<b>Note:</b> Please arrive 10 minutes before your scheduled appointment."


def get_appointment_date(appointment: Appointment) -> str:
    return timezone.localtime(appointment.start_datetime).strftime(
        APPOINTMENT_DATE_FORMAT
    )


def get_appointment_time(appointment: Appointment) -> str:
    return timezone.localtime(appointment.start_datetime).strftime(
        APPOINTMENT_TIME_FORMAT
    )


def append_notes(message: str, notes: str | None) -> str:
    if notes:
        return f"{message}\n\n{html.escape(notes)}"
    return message


def build_appointment_confirmed_notes(appointment: Appointment, notes: str | None) -> str:
    patient_name = html.escape(appointment.customer_profile.get_full_name())
    service_name = html.escape(appointment.service.name)
    message = (
        f"Hi <b>{patient_name}</b>,\n"
        f"Your appointment has been confirmed. Please find the details below:\n\n"
        f"<b>Service:</b> {service_name}\n"
        f"{build_location_note(appointment)}"
        f"We look forward to seeing you.\n\n"
        f"{build_attendance_note(appointment)}"
    )
    return append_notes(message, notes)


def build_appointment_rescheduled_notes(appointment: Appointment, notes: str | None) -> str:
    patient_name = html.escape(appointment.customer_profile.get_full_name())
    service_name = html.escape(appointment.service.name)
    message = (
        f"Hi <b>{patient_name}</b>,\n\n"
        f"Your appointment has been rescheduled. Please find your updated "
        f"appointment details below:\n\n"
        f"<b>Service:</b> {service_name}\n"
        f"{build_location_note(appointment)}"
        f"Please refer to the updated date and time.\n\n"
        f"{build_attendance_note(appointment)}"
    )
    return append_notes(message, notes)
