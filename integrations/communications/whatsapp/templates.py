from django.conf import settings
from django.utils import timezone

from integrations.utils.constants import CommunicationEventType

EVENT_TEMPLATE_SETTING = {
    CommunicationEventType.APPOINTMENT_CONFIRMED: "WHATSAPP_TEMPLATE_CONFIRMED",
    CommunicationEventType.APPOINTMENT_CANCELLED: "WHATSAPP_TEMPLATE_CANCELLED",
    CommunicationEventType.APPOINTMENT_RESCHEDULED: "WHATSAPP_TEMPLATE_RESCHEDULED",
}


def template_language():
    return getattr(settings, "WHATSAPP_TEMPLATE_LANGUAGE", None) or "en"


def template_name_for_event(event_type):
    setting_name = EVENT_TEMPLATE_SETTING[event_type]
    return getattr(settings, setting_name)


def format_appointment_date(value):
    if value is None:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%d %b %Y")


def format_appointment_time(value):
    if value is None:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%I:%M %p")


def customer_display_name(customer_profile):
    parts = [
        customer_profile.first_name or "",
        customer_profile.last_name or "",
    ]
    return " ".join(part for part in parts if part).strip() or "Customer"


def center_address_text(center):
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


def clinic_address_display(center):
    """Meta {{clinic_address}}: 'Clinic name, Clinic address'."""
    if center is None:
        return "Center"
    name = (center.name or "").strip() or "Center"
    address = center_address_text(center)
    if address:
        return f"{name}, {address}"
    return name


def named_text_parameter(parameter_name, text):
    return {"parameter_name": parameter_name, "text": str(text)}


def build_template_parameters(
    event_type,
    appointment,
    *,
    previous_start_datetime=None,
):
    """
    Named body params matching approved Meta templates:
    patient_name, appointment_date, appointment_time, service_name,
    clinic_address (confirmed / rescheduled only).
    """
    _ = previous_start_datetime  # Meta reschedule template shows new slot only
    profile = appointment.customer_profile
    patient_name = customer_display_name(profile)
    service_name = appointment.service.name if appointment.service_id else "Service"
    center = appointment.center if appointment.center_id else None
    start = appointment.start_datetime
    appointment_date = format_appointment_date(start)
    appointment_time = format_appointment_time(start)
    clinic_address = clinic_address_display(center)

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
    builders = {
        CommunicationEventType.APPOINTMENT_CONFIRMED: confirmed_or_rescheduled,
        CommunicationEventType.APPOINTMENT_CANCELLED: cancelled,
        CommunicationEventType.APPOINTMENT_RESCHEDULED: confirmed_or_rescheduled,
    }
    return builders[event_type]
