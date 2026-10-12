import requests
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import Error as DatabaseError

from accounts.associates.models import Associate
from appointments.models import Appointment
from appointments.utils.constants import AppointmentStatus
from appointments.utils.emails import (
    build_appointment_confirmed_notes,
    build_appointment_rescheduled_notes,
)
from core.utils.constants import AppointmentModes
from core.utils.log import logger
from integrations.google_calendar import calendar_api
from integrations.google_calendar.connections import get_fixed_calendar_organizer
from integrations.google_calendar.tokens import get_valid_access_token

GOOGLE_SYNC_ERRORS = (
    requests.RequestException, ValueError, InvalidToken, ImproperlyConfigured,
)
GOOGLE_EVENT_ID_CONFLICT = 409
STALE_GOOGLE_EVENT_STATUSES = (404, 410)


def is_google_calendar_configured():
    return bool(getattr(settings, "GOOGLE_CALENDAR_ID", None))


def google_calendar_event_id(appointment):
    return appointment.pk.hex


def describe_google_error(error: Exception):
    if isinstance(error, InvalidToken):
        return (
            "Stored Google token could not be decrypted, the account may "
            "need to be reconnected."
        )
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if payload:
            message = payload.get("error", {}).get("message")
            if message:
                return message
        if response.text:
            return response.text
    return str(error) or type(error).__name__


def build_attendee_emails(
    contact_email: str | None, associates: list[Associate], organizer=None
):
    emails = []
    if contact_email:
        emails.append(contact_email)
    organizer_pk = organizer.pk if organizer is not None else None
    for associate in associates:
        if organizer_pk and associate.pk == organizer_pk:
            continue
        if associate.user.email:
            emails.append(associate.user.email)
    return emails


def load_appointment_for_google_sync(appointment_id):
    return (
        Appointment.objects.select_related(
            "customer_profile__customer",
            "service",
            "center",
        )
        .prefetch_related("associate_links__associate__user")
        .filter(pk=appointment_id)
        .first()
    )


def appointment_has_reschedule_history(appointment):
    return appointment.history_entries.exists()


def google_event_title(has_reschedule_history):
    if has_reschedule_history:
        return "Appointment Rescheduled"
    return "Appointment Confirmed"


def google_event_notes(appointment, has_reschedule_history):
    if has_reschedule_history:
        return build_appointment_rescheduled_notes(appointment, appointment.notes)
    return build_appointment_confirmed_notes(appointment, appointment.notes)


def associates_for_appointment(appointment):
    return [
        link.associate
        for link in appointment.associate_links.all()
        if link.associate is not None
    ]


def persist_google_event(appointment, event_id, meet_link):
    if (
        appointment.google_event_id == event_id
        and appointment.google_meet_link == meet_link
    ):
        return
    appointment.google_event_id = event_id
    appointment.google_meet_link = meet_link
    try:
        appointment.save(
            update_fields=["google_event_id", "google_meet_link", "updated_at"]
        )
    except DatabaseError as error:
        logger.warning(
            f"Failed to persist google_event_id for appointment "
            f"{appointment.pk} after Google Calendar sync: {error}"
        )


def is_stale_google_event_error(error):
    response = getattr(error, "response", None)
    return (
        response is not None
        and response.status_code in STALE_GOOGLE_EVENT_STATUSES
    )


def is_google_event_conflict_error(error):
    response = getattr(error, "response", None)
    return response is not None and response.status_code == GOOGLE_EVENT_ID_CONFLICT


def delete_google_event(appointment, organizer, access_token):
    event_id = appointment.google_event_id or google_calendar_event_id(appointment)
    associates = associates_for_appointment(appointment)
    calendar_api.delete_event(
        access_token,
        event_id,
        participant_emails=build_attendee_emails(
            appointment.customer_profile.customer.contact_email,
            associates,
            organizer,
        ),
    )


def upsert_event_with_fallback(
    access_token, stored_event_id, insert_event_id, patch_kwargs, insert_kwargs
):
    # patch stored id -> (stale) insert with deterministic id -> (conflict) patch it.
    if stored_event_id:
        try:
            return calendar_api.patch_event(
                access_token, stored_event_id, **patch_kwargs
            )
        except requests.HTTPError as error:
            if not is_stale_google_event_error(error):
                raise
    try:
        return calendar_api.insert_event(
            access_token, event_id=insert_event_id, **insert_kwargs
        )
    except requests.HTTPError as error:
        if not is_google_event_conflict_error(error):
            raise
        event = calendar_api.get_event(access_token, insert_event_id)
        return calendar_api.patch_event(access_token, event["id"], **patch_kwargs)


def upsert_google_event(appointment, organizer, access_token):
    associates = associates_for_appointment(appointment)
    has_reschedule_history = appointment_has_reschedule_history(appointment)
    title = google_event_title(has_reschedule_history)
    notes = google_event_notes(appointment, has_reschedule_history)
    attendee_emails = build_attendee_emails(
        appointment.customer_profile.customer.contact_email,
        associates,
        organizer,
    )
    deterministic_id = google_calendar_event_id(appointment)
    needs_new_meet_link = (
        appointment.modality == AppointmentModes.VIRTUAL
        and not appointment.google_meet_link
    )
    needs_clear_meet_link = (
        appointment.modality != AppointmentModes.VIRTUAL
        and bool(appointment.google_meet_link)
    )
    patch_kwargs = {
        "title": title,
        "start": appointment.start_datetime,
        "end": appointment.end_datetime,
        "location": None,
        "notes": notes,
        "add_meet_link": needs_new_meet_link,
        "clear_meet_link": needs_clear_meet_link,
        "participant_emails": attendee_emails,
        "is_appointment": True,
    }
    insert_kwargs = {
        "title": title,
        "start": appointment.start_datetime,
        "end": appointment.end_datetime,
        "location": None,
        "notes": notes,
        "need_meet_link": appointment.modality == AppointmentModes.VIRTUAL,
        "participant_emails": attendee_emails,
        "is_appointment": True,
    }
    event = upsert_event_with_fallback(
        access_token,
        appointment.google_event_id,
        deterministic_id,
        patch_kwargs,
        insert_kwargs,
    )
    persist_google_event(
        appointment, event["id"], calendar_api.extract_meet_link(event)
    )


def apply_google_desired_state(appointment):
    organizer = get_fixed_calendar_organizer()
    if organizer is None:
        logger.error(
            f"Google Calendar organizer is disconnected; cannot sync "
            f"appointment {appointment.pk}."
        )
        return "Google Calendar organizer is disconnected"
    access_token = get_valid_access_token(organizer)
    if appointment.status == AppointmentStatus.CANCELLED:
        delete_google_event(appointment, organizer, access_token)
        return None
    upsert_google_event(appointment, organizer, access_token)
    appointment.refresh_from_db(
        fields=["status", "google_event_id", "google_meet_link"]
    )
    if appointment.status == AppointmentStatus.CANCELLED:
        delete_google_event(appointment, organizer, access_token)
    return None


def sync_appointment_with_google(appointment_id):
    """
    Match Google Calendar to the live appointment. Returns a skip reason
    string, or None on success. Raises GOOGLE_SYNC_ERRORS on API failure.
    """
    appointment = load_appointment_for_google_sync(appointment_id)
    if appointment is None:
        return "Appointment no longer exists"
    return apply_google_desired_state(appointment)


def send_google_calendar_outbound_event(
    connection,
    title,
    start,
    end,
    notes=None,
    event_id=None,
    *,
    all_day=False,
    recurrence=None,
):
    """
    Upsert an event onto the personal calendar owned by `connection`.
    Uses insert with a deterministic id, falling back to patch on conflict
    or when a stored event_id is already known.
    """
    access_token = get_valid_access_token(connection)
    event_kwargs = {
        "title": title,
        "start": start,
        "end": end,
        "notes": notes,
        "all_day": all_day,
        "recurrence": recurrence,
        "biopeak_outbound": True,
    }
    event = upsert_event_with_fallback(
        access_token, event_id, event_id, event_kwargs, event_kwargs
    )
    return event["id"]
