from django.conf import settings
from django.utils import timezone

from core.utils.constants import AppointmentModes
from integrations.utils.constants import (
    CommunicationEventType,
    WHATSAPP_TEMPLATE_BY_EVENT,
)


def template_language() -> str:
    return getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", None) or "en"


def template_name_for_event(event_type: str) -> str:
    return WHATSAPP_TEMPLATE_BY_EVENT[event_type]


def format_appointment_date(value) -> str:
    if value is None:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%d %b %Y")


def format_appointment_time(value) -> str:
    if value is None:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%I:%M %p")


def format_appointment_start_datetime(value) -> str:
    if value is None:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%d %b %Y, %I:%M %p")


def customer_display_name(customer_profile) -> str:
    parts = [
        customer_profile.first_name or "",
        customer_profile.last_name or "",
    ]
    return " ".join(part for part in parts if part).strip() or "Customer"


def center_address_text(center) -> str:
    if center is None:
        return ""
    parts = []
    for value in (
        center.address,
        center.address_line_1,
        center.address_line_2,
        center.city,
        center.state,
        center.pincode,
        center.country,
    ):
        text = (value or "").strip()
        if text and text not in parts:
            parts.append(text)
    return ", ".join(parts)


def clinic_address_display(center) -> str:
    """Meta {{clinic_address}}: 'Clinic name, Clinic address'."""
    if center is None:
        return "Center"
    name = (center.name or "").strip() or "Center"
    address = center_address_text(center)
    if address:
        return f"{name}, {address}"
    return name


VIRTUAL_MEET_LINK_FALLBACK = "Check your calendar invite for the Google Meet link"


def location_or_meet_link(appointment) -> str:
    if appointment.modality == AppointmentModes.VIRTUAL:
        meet_link = (appointment.google_meet_link or "").strip()
        if meet_link:
            return meet_link
        return VIRTUAL_MEET_LINK_FALLBACK
    center = appointment.center if appointment.center_id else None
    return clinic_address_display(center)


def named_text_parameter(parameter_name: str, text) -> dict:
    return {"parameter_name": parameter_name, "text": str(text)}


def build_positional_session_parameters(appointment) -> list:
    """
    Positional Meta body params {{1}}…{{4}} for reminder / no-show:
    name, start datetime, service name, address or Meet link.
    """
    profile = appointment.customer_profile
    service_name = appointment.service.name if appointment.service_id else "Service"
    return [
        customer_display_name(profile),
        format_appointment_start_datetime(appointment.start_datetime),
        service_name,
        location_or_meet_link(appointment),
    ]


def build_named_lifecycle_parameters(appointment) -> dict:
    profile = appointment.customer_profile
    patient_name = customer_display_name(profile)
    service_name = appointment.service.name if appointment.service_id else "Service"
    start = appointment.start_datetime
    appointment_date = format_appointment_date(start)
    appointment_time = format_appointment_time(start)
    # Meta param name stays clinic_address; virtual fills Meet link.
    clinic_address = location_or_meet_link(appointment)
    confirmed_or_rescheduled = [
        named_text_parameter("patient_name", patient_name),
        named_text_parameter("appointment_date", appointment_date),
        named_text_parameter("appointment_time", appointment_time),
        named_text_parameter("service_name", service_name),
        named_text_parameter("clinic_address", clinic_address),
    ]
    cancelled = [
        named_text_parameter("patient_name", patient_name),
        named_text_parameter("appointment_date", appointment_date),
        named_text_parameter("appointment_time", appointment_time),
        named_text_parameter("service_name", service_name),
    ]
    return {
        CommunicationEventType.APPOINTMENT_CONFIRMED: confirmed_or_rescheduled,
        CommunicationEventType.APPOINTMENT_CANCELLED: cancelled,
        CommunicationEventType.APPOINTMENT_RESCHEDULED: confirmed_or_rescheduled,
    }


POSITIONAL_SESSION_EVENT_TYPES = frozenset(
    {
        CommunicationEventType.APPOINTMENT_REMINDER,
        CommunicationEventType.APPOINTMENT_NO_SHOW,
    }
)


def build_template_parameters(
    event_type,
    appointment,
    *,
    previous_start_datetime=None,
) -> list:
    """
    Named body params matching approved Meta templates:
    patient_name, appointment_date, appointment_time, service_name,
    clinic_address (confirmed / rescheduled only — center address or Meet).

    Reminder / no-show use positional {{1}}…{{4}} ({{4}} = address or Meet).
    """
    _ = previous_start_datetime  # Meta reschedule template shows new slot only
    if event_type in POSITIONAL_SESSION_EVENT_TYPES:
        return build_positional_session_parameters(appointment)
    return build_named_lifecycle_parameters(appointment)[event_type]
