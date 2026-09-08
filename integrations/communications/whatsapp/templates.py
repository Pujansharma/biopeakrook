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


def format_appointment_datetime(value):
    if value is None:
        return ""
    local_value = timezone.localtime(value)
    return local_value.strftime("%d %b %Y %I:%M %p")


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


def build_template_parameters(
    event_type,
    appointment,
    *,
    previous_start_datetime=None,
):
    profile = appointment.customer_profile
    customer_name = customer_display_name(profile)
    service_name = appointment.service.name if appointment.service_id else "Service"
    center_name = appointment.center.name if appointment.center_id else "Center"
    start = appointment.start_datetime

    builders = {
        CommunicationEventType.APPOINTMENT_CONFIRMED: lambda: [
            customer_name,
            service_name,
            format_appointment_time(start),
            format_appointment_date(start),
            center_name,
        ],
        CommunicationEventType.APPOINTMENT_CANCELLED: lambda: [
            customer_name,
            service_name,
            format_appointment_date(start),
            format_appointment_time(start),
        ],
        CommunicationEventType.APPOINTMENT_RESCHEDULED: lambda: [
            customer_name,
            service_name,
            format_appointment_datetime(previous_start_datetime or start),
            format_appointment_datetime(start),
            center_name,
        ],
    }
    return builders[event_type]()
