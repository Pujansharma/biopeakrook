from datetime import datetime

import requests
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from accounts.associates.models import Associate
from accounts.customers.models import CustomerProfile
from appointments.models import Appointment
from core.utils.constants import AppointmentModes
from core.utils.log import logger
from integrations.google_calendar import calendar_api
from integrations.google_calendar.tokens import get_valid_access_token

GOOGLE_SYNC_ERRORS = (
    requests.RequestException, ValueError, InvalidToken, ImproperlyConfigured,
)
GOOGLE_CALENDAR_ID = getattr(settings, "GOOGLE_CALENDAR_ID", None)


def get_fixed_calendar_organizer():
    if not GOOGLE_CALENDAR_ID:
        return None
    organizer = Associate.objects.filter(
        google_email__iexact=GOOGLE_CALENDAR_ID, is_active=True, user__is_active=True
    ).first()
    if organizer is None or not organizer.google_refresh_token:
        return None
    return organizer


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
    contact_email: str | None, associates: list[Associate], organizer: Associate | None
):
    emails = []
    if contact_email:
        emails.append(contact_email)
    for associate in associates:
        if organizer and associate.pk == organizer.pk:
            continue
        if associate.user.email:
            emails.append(associate.user.email)
    return emails


def resolve_associates_from_payload(associates_payload: list[dict] | None):
    if not associates_payload:
        return []
    associate_ids = [entry["associate_id"] for entry in associates_payload]
    return list(Associate.objects.filter(pk__in=associate_ids).select_related("user"))


def sync_new_appointment_with_google(
    customer_profile: CustomerProfile,
    modality: str,
    start: datetime,
    end: datetime,
    notes: str | None,
    associates_payload: list[dict] | None,
):
    organizer = get_fixed_calendar_organizer()
    if organizer is None:
        return None, None
    associates = resolve_associates_from_payload(associates_payload)
    try:
        access_token = get_valid_access_token(organizer)
        event = calendar_api.insert_event(
            access_token,
            title=f"Appointment Confirmed",
            start=start,
            end=end,
            location=None,
            notes=notes,
            need_meet_link=modality == AppointmentModes.VIRTUAL,
            participant_emails=build_attendee_emails(
                customer_profile.customer.contact_email, associates, organizer
            ),
        )
    except GOOGLE_SYNC_ERRORS as error:
        reason = describe_google_error(error)
        logger.warning(f"Google Calendar insert_event failed during booking: {reason}")
        return None, None
    return event["id"], calendar_api.extract_meet_link(event)


def sync_rescheduled_appointment_with_google(
    instance: Appointment,
    customer_profile: CustomerProfile,
    modality: str,
    start: datetime,
    end: datetime,
    notes: str | None,
    associates_payload: list[dict] | None,
):
    organizer = get_fixed_calendar_organizer()
    if organizer is None:
        return instance.google_event_id, instance.google_meet_link
    associates = resolve_associates_from_payload(associates_payload)

    title = f"Appointment Rescheduled"
    location = None
    attendee_emails = build_attendee_emails(
        customer_profile.customer.contact_email, associates, organizer
    )
    # Reuse the existing Meet link if there is one patch_event() only
    # rotates it when add_meet_link=True, and rotating strands anyone
    # holding the old link. Only add a fresh one if the appointment doesn't
    # have one yet and the (possibly just-changed) modality is virtual. If
    # the modality moved away from virtual, drop the Meet link instead.
    needs_new_meet_link = (
        modality == AppointmentModes.VIRTUAL and not instance.google_meet_link
    )
    needs_clear_meet_link = (
        modality != AppointmentModes.VIRTUAL and bool(instance.google_meet_link)
    )
    needs_insert = not instance.google_event_id
    try:
        access_token = get_valid_access_token(organizer)
        if not needs_insert:
            try:
                event = calendar_api.patch_event(
                    access_token,
                    instance.google_event_id,
                    title=title,
                    start=start,
                    end=end,
                    location=location,
                    notes=notes,
                    add_meet_link=needs_new_meet_link,
                    clear_meet_link=needs_clear_meet_link,
                    participant_emails=attendee_emails,
                )
            except requests.HTTPError as error:
                stale_event = (
                    error.response is not None
                    and error.response.status_code in (404, 410)
                )
                if not stale_event:
                    raise
                # The event is gone from this organizer's calendar (e.g. the
                # assigned associates changed since it was created) - mirror
                # it fresh instead of failing the whole reschedule.
                needs_insert = True
        if needs_insert:
            event = calendar_api.insert_event(
                access_token,
                title=title,
                start=start,
                end=end,
                location=location,
                notes=notes,
                need_meet_link=modality == AppointmentModes.VIRTUAL,
                participant_emails=attendee_emails,
            )
    except GOOGLE_SYNC_ERRORS as error:
        reason = describe_google_error(error)
        logger.warning(
            f"Google Calendar sync failed for appointment {instance.pk} reschedule: {reason}"
        )
        return instance.google_event_id, instance.google_meet_link
    return event["id"], calendar_api.extract_meet_link(event)


def sync_cancelled_appointment_with_google(instance: Appointment):
    if not instance.google_event_id:
        return False
    organizer = get_fixed_calendar_organizer()
    if organizer is None:
        logger.error(
            f"Google Calendar organizer is disconnected; cannot delete event "
            f"{instance.google_event_id} for cancelled appointment {instance.pk}. "
            f"The Google event may still exist even though the appointment is "
            f"cancelled."
        )
        return False
    associates = [
        link.associate
        for link in instance.associate_links.select_related("associate__user")
    ]
    try:
        access_token = get_valid_access_token(organizer)
        calendar_api.delete_event(
            access_token,
            instance.google_event_id,
            participant_emails=build_attendee_emails(
                instance.customer_profile.customer.contact_email, associates, organizer
            ),
        )
    except GOOGLE_SYNC_ERRORS as error:
        reason = describe_google_error(error)
        logger.error(
            f"Google Calendar delete_event failed for appointment {instance.pk}: "
            f"{reason}. The Google event may still exist even though the "
            f"appointment is cancelled."
        )
        return False
    return True
