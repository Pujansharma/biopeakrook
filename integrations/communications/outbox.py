from datetime import timedelta

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone

from appointments.models import Appointment
from core.utils.constants import AppointmentModes
from core.utils.log import logger
from integrations.communications.wake import publish_outbox_wake
from integrations.communications.whatsapp.sdk import (
    extract_wamid,
    is_whatsapp_configured,
    send_template,
)
from integrations.communications.whatsapp.templates import (
    build_template_parameters,
    template_language,
    template_name_for_event,
)
from integrations.google_calendar.google_sync import (
    GOOGLE_SYNC_ERRORS,
    describe_google_error,
    is_google_calendar_configured,
    sync_appointment_with_google,
)
from integrations.google_calendar.personal_outbound import (
    sync_associate_blocks_to_personal_google,
    sync_associate_leave_to_personal_google,
)
from integrations.models import CommunicationOutbox, CommunicationWebhookEvent
from integrations.utils.constants import (
    CommunicationChannel,
    CommunicationEventType,
    CommunicationOutboxStatus,
    TERMINAL_APPOINTMENT_EVENT_TYPES,
    TERMINAL_OUTBOX_BLOCKING_STATUSES,
)

STATUS_RANK = {
    CommunicationOutboxStatus.PENDING: 0,
    CommunicationOutboxStatus.SENDING: 1,
    CommunicationOutboxStatus.ACCEPTED: 2,
    CommunicationOutboxStatus.SENT: 3,
    CommunicationOutboxStatus.DELIVERED: 4,
    CommunicationOutboxStatus.READ: 5,
    CommunicationOutboxStatus.FAILED: 6,
    CommunicationOutboxStatus.SKIPPED: 0,
}

WEBHOOK_STATUS_MAP = {
    "sent": CommunicationOutboxStatus.SENT,
    "delivered": CommunicationOutboxStatus.DELIVERED,
    "read": CommunicationOutboxStatus.READ,
    "failed": CommunicationOutboxStatus.FAILED,
}

MAX_OUTBOX_ATTEMPTS = 2
STALE_SENDING_MINUTES = 5
TERMINAL_EVENT_TYPES = TERMINAL_APPOINTMENT_EVENT_TYPES
ACTIVE_OUTBOX_STATUSES = TERMINAL_OUTBOX_BLOCKING_STATUSES
OPEN_GOOGLE_OUTBOX_STATUSES = (
    CommunicationOutboxStatus.PENDING,
    CommunicationOutboxStatus.FAILED,
)


def phone_to_whatsapp_recipient(phone):
    if not phone:
        return ""
    digits = "".join(character for character in str(phone) if character.isdigit())
    return digits


def resolve_recipient_phone(appointment):
    profile = appointment.customer_profile
    customer = getattr(profile, "customer", None)
    user = getattr(customer, "user", None)
    return phone_to_whatsapp_recipient(getattr(user, "phone", None))


def existing_terminal_outbox(appointment, event_type, channel):
    return (
        CommunicationOutbox.objects.filter(
            appointment=appointment,
            channel=channel,
            event_type=event_type,
            status__in=ACTIVE_OUTBOX_STATUSES,
        )
        .order_by("-created_at")
        .first()
    )


def existing_outbox_any_status(appointment, event_type, channel):
    """Any prior row for this terminal WhatsApp event (incl. SKIPPED)."""
    return (
        CommunicationOutbox.objects.filter(
            appointment=appointment,
            channel=channel,
            event_type=event_type,
        )
        .order_by("-created_at")
        .first()
    )


def existing_open_google_outbox(appointment):
    return (
        CommunicationOutbox.objects.filter(
            appointment=appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            status__in=OPEN_GOOGLE_OUTBOX_STATUSES,
            attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
        )
        .order_by("created_at")
        .first()
    )


def create_outbox_message(
    appointment=None,
    *,
    channel,
    event_type,
    to_phone="",
    template_name="",
    language="",
    parameters=None,
    status,
    skip_reason="",
    associate_availability_block=None,
    associate_leave=None,
    availability_series_id=None,
):
    try:
        return CommunicationOutbox.objects.create(
            appointment=appointment,
            associate_availability_block=associate_availability_block,
            associate_leave=associate_leave,
            availability_series_id=availability_series_id,
            channel=channel,
            event_type=event_type,
            to_phone=to_phone,
            template_name=template_name or "",
            template_language=language,
            template_parameters=parameters or [],
            status=status,
            skip_reason=skip_reason,
        )
    except IntegrityError:
        if appointment is not None:
            existing = existing_terminal_outbox(appointment, event_type, channel)
            if existing is not None:
                return existing
            raise
        existing = existing_open_google_availability_outbox(
            associate_availability_block=associate_availability_block,
            associate_leave=associate_leave,
            availability_series_id=availability_series_id,
        )
        if existing is not None:
            return existing
        raise


def google_outbox_target_filter(
    *,
    appointment_id=None,
    associate_availability_block_id=None,
    associate_leave_id=None,
    availability_series_id=None,
):
    if appointment_id is not None:
        return {"appointment_id": appointment_id}
    if availability_series_id is not None:
        return {"availability_series_id": availability_series_id}
    if associate_availability_block_id is not None:
        return {
            "associate_availability_block_id": associate_availability_block_id
        }
    if associate_leave_id is not None:
        return {"associate_leave_id": associate_leave_id}
    return None


def google_outbox_target_filter_for_message(message):
    return google_outbox_target_filter(
        appointment_id=message.appointment_id,
        associate_availability_block_id=message.associate_availability_block_id,
        associate_leave_id=message.associate_leave_id,
        availability_series_id=message.availability_series_id,
    )


def existing_open_google_availability_outbox(
    *,
    associate_availability_block=None,
    associate_leave=None,
    availability_series_id=None,
):
    filters = {
        "channel": CommunicationChannel.GOOGLE_CALENDAR,
        "status__in": OPEN_GOOGLE_OUTBOX_STATUSES,
        "attempt_count__lt": MAX_OUTBOX_ATTEMPTS,
    }
    if availability_series_id is not None:
        filters["availability_series_id"] = availability_series_id
    elif associate_availability_block is not None:
        filters["associate_availability_block"] = associate_availability_block
    elif associate_leave is not None:
        filters["associate_leave"] = associate_leave
    else:
        return None
    return (
        CommunicationOutbox.objects.filter(**filters)
        .order_by("created_at")
        .first()
    )


def enqueue_associate_block_sync(*, block=None, series_id=None):
    existing = existing_open_google_availability_outbox(
        associate_availability_block=block if series_id is None else None,
        availability_series_id=series_id,
    )
    if existing is not None:
        return existing
    return create_outbox_message(
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        event_type=CommunicationEventType.ASSOCIATE_BLOCK_SYNC,
        status=CommunicationOutboxStatus.PENDING,
        associate_availability_block=block if series_id is None else None,
        availability_series_id=series_id,
    )


def enqueue_associate_leave_sync(leave):
    existing = existing_open_google_availability_outbox(associate_leave=leave)
    if existing is not None:
        return existing
    return create_outbox_message(
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        event_type=CommunicationEventType.ASSOCIATE_LEAVE_SYNC,
        status=CommunicationOutboxStatus.PENDING,
        associate_leave=leave,
    )


ONCE_PER_APPOINTMENT_WHATSAPP_EVENTS = frozenset(
    {
        CommunicationEventType.APPOINTMENT_REMINDER,
        CommunicationEventType.APPOINTMENT_NO_SHOW,
    }
)


def enqueue_whatsapp_message(
    appointment,
    event_type,
    *,
    previous_start_datetime=None,
):
    to_phone = resolve_recipient_phone(appointment)
    template_name = template_name_for_event(event_type)
    language = template_language()
    parameters = build_template_parameters(
        event_type,
        appointment,
        previous_start_datetime=previous_start_datetime,
    )

    # Reminder / no-show: one row forever (incl. SKIPPED) — check before early skips.
    if event_type in ONCE_PER_APPOINTMENT_WHATSAPP_EVENTS:
        existing_any = existing_outbox_any_status(
            appointment, event_type, CommunicationChannel.WHATSAPP
        )
        if existing_any is not None:
            return existing_any

    if not is_whatsapp_configured():
        return create_outbox_message(
            appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=event_type,
            to_phone=to_phone,
            template_name=template_name,
            language=language,
            parameters=parameters,
            status=CommunicationOutboxStatus.SKIPPED,
            skip_reason="WhatsApp is not configured",
        )

    if not to_phone:
        return create_outbox_message(
            appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=event_type,
            to_phone="",
            template_name=template_name,
            language=language,
            parameters=parameters,
            status=CommunicationOutboxStatus.SKIPPED,
            skip_reason="Customer phone is missing",
        )

    if event_type in TERMINAL_EVENT_TYPES:
        existing = existing_terminal_outbox(
            appointment, event_type, CommunicationChannel.WHATSAPP
        )
        if existing is not None:
            return existing

    return create_outbox_message(
        appointment,
        channel=CommunicationChannel.WHATSAPP,
        event_type=event_type,
        to_phone=to_phone,
        template_name=template_name,
        language=language,
        parameters=parameters,
        status=CommunicationOutboxStatus.PENDING,
    )


def enqueue_google_calendar_message(appointment, event_type):
    if not is_google_calendar_configured():
        return create_outbox_message(
            appointment,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            event_type=event_type,
            status=CommunicationOutboxStatus.SKIPPED,
            skip_reason="Google Calendar is not configured",
        )

    existing = existing_open_google_outbox(appointment)
    if existing is not None:
        return existing

    if event_type in TERMINAL_EVENT_TYPES:
        existing_terminal = existing_terminal_outbox(
            appointment, event_type, CommunicationChannel.GOOGLE_CALENDAR
        )
        if existing_terminal is not None:
            return existing_terminal

    return create_outbox_message(
        appointment,
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        event_type=event_type,
        status=CommunicationOutboxStatus.PENDING,
    )


def enqueue_whatsapp_only_message(
    appointment,
    event_type,
    *,
    previous_start_datetime=None,
    wake=True,
):
    """
    Persist WhatsApp outbox only (no Google Calendar). Used for reminder /
    no-show. wake=False when sweep enqueues reminders (same job drains).
    """
    whatsapp_message = enqueue_whatsapp_message(
        appointment,
        event_type,
        previous_start_datetime=previous_start_datetime,
    )
    pending_statuses = {
        CommunicationOutboxStatus.PENDING,
        CommunicationOutboxStatus.FAILED,
    }
    if wake and whatsapp_message.status in pending_statuses:
        publish_outbox_wake()
    return whatsapp_message


def enqueue_appointment_message(
    appointment,
    event_type,
    *,
    previous_start_datetime=None,
):
    """
    Persist Google Calendar then WhatsApp outbox rows. Worker syncs Meet
    before WA send when virtual. Call via schedule_queue_* (on_commit) so
    outbox failures do not roll back booking/cancel/reschedule.
    """
    google_message = enqueue_google_calendar_message(appointment, event_type)
    whatsapp_message = enqueue_whatsapp_message(
        appointment,
        event_type,
        previous_start_datetime=previous_start_datetime,
    )
    pending_statuses = {
        CommunicationOutboxStatus.PENDING,
        CommunicationOutboxStatus.FAILED,
    }
    if (
        whatsapp_message.status in pending_statuses
        or google_message.status in pending_statuses
    ):
        publish_outbox_wake()
    return whatsapp_message, google_message


def reclaim_stale_whatsapp_sending_messages(stale_before, now):
    return CommunicationOutbox.objects.filter(
        channel=CommunicationChannel.WHATSAPP,
        status=CommunicationOutboxStatus.SENDING,
        updated_at__lt=stale_before,
    ).update(
        status=CommunicationOutboxStatus.SKIPPED,
        skip_reason="Stale SENDING: send may have reached Meta; not retried",
        error_code="stale_sending",
        error_detail="Send timed out or worker crashed after claim",
        updated_at=now,
    )


def reclaim_stale_google_sending_messages(stale_before, now):
    exhausted = CommunicationOutbox.objects.filter(
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        status=CommunicationOutboxStatus.SENDING,
        updated_at__lt=stale_before,
        attempt_count__gte=MAX_OUTBOX_ATTEMPTS,
    ).update(
        status=CommunicationOutboxStatus.SKIPPED,
        skip_reason=f"Exceeded max send attempts ({MAX_OUTBOX_ATTEMPTS})",
        error_code="stale_sending",
        error_detail="Send timed out or worker crashed after claim",
        updated_at=now,
    )
    retryable = CommunicationOutbox.objects.filter(
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        status=CommunicationOutboxStatus.SENDING,
        updated_at__lt=stale_before,
        attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
    ).update(
        status=CommunicationOutboxStatus.FAILED,
        skip_reason="",
        error_code="stale_sending",
        error_detail="Send timed out or worker crashed after claim; retrying",
        updated_at=now,
    )
    return exhausted + retryable


def reclaim_stale_sending_messages():
    stale_before = timezone.now() - timedelta(minutes=STALE_SENDING_MINUTES)
    now = timezone.now()
    return reclaim_stale_whatsapp_sending_messages(
        stale_before, now
    ) + reclaim_stale_google_sending_messages(stale_before, now)


def mark_outbox_exhausted(message):
    message.status = CommunicationOutboxStatus.SKIPPED
    message.skip_reason = f"Exceeded max send attempts ({MAX_OUTBOX_ATTEMPTS})"
    message.save(update_fields=["status", "skip_reason", "updated_at"])
    return message


def mark_outbox_skipped(message, skip_reason):
    message.status = CommunicationOutboxStatus.SKIPPED
    message.skip_reason = skip_reason
    message.save(update_fields=["status", "skip_reason", "updated_at"])
    return message


def mark_outbox_accepted(message, *, wamid="", provider_response=None):
    now = timezone.now()
    message.wamid = wamid or message.wamid
    message.status = CommunicationOutboxStatus.ACCEPTED
    message.accepted_at = now
    message.error_code = ""
    message.error_detail = ""
    message.skip_reason = ""
    update_fields = [
        "wamid",
        "status",
        "accepted_at",
        "error_code",
        "error_detail",
        "skip_reason",
        "updated_at",
    ]
    if provider_response is not None:
        message.provider_response = provider_response
        update_fields.append("provider_response")
    message.save(update_fields=update_fields)
    return message


def mark_outbox_failed(message, *, error_code, error_detail, provider_response=None):
    now = timezone.now()
    message.failed_at = now
    message.error_code = str(error_code)
    message.error_detail = str(error_detail)
    update_fields = [
        "failed_at",
        "error_code",
        "error_detail",
        "updated_at",
    ]
    if message.attempt_count >= MAX_OUTBOX_ATTEMPTS:
        message.status = CommunicationOutboxStatus.SKIPPED
        message.skip_reason = f"Exceeded max send attempts ({MAX_OUTBOX_ATTEMPTS})"
        update_fields.extend(["status", "skip_reason"])
        logger.warning(
            f"Outbox {message.pk} exhausted: {message.error_code} {message.error_detail}"
        )
    else:
        message.status = CommunicationOutboxStatus.FAILED
        update_fields.append("status")
        logger.warning(
            f"Outbox {message.pk} failed: {message.error_code} {message.error_detail}"
        )
    if provider_response is not None:
        message.provider_response = provider_response
        update_fields.append("provider_response")
    message.save(update_fields=update_fields)
    return message


def claim_outbox_message(message_id):
    now = timezone.now()
    updated = CommunicationOutbox.objects.filter(
        pk=message_id,
        status__in=[
            CommunicationOutboxStatus.PENDING,
            CommunicationOutboxStatus.FAILED,
        ],
        attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
    ).update(
        status=CommunicationOutboxStatus.SENDING,
        attempt_count=F("attempt_count") + 1,
        updated_at=now,
    )
    if updated != 1:
        return None
    return CommunicationOutbox.objects.filter(pk=message_id).first()


def has_in_flight_google_sync(appointment_id):
    return CommunicationOutbox.objects.filter(
        appointment_id=appointment_id,
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        status=CommunicationOutboxStatus.SENDING,
    ).exists()


def has_in_flight_google_sync_for_message(message):
    target = google_outbox_target_filter_for_message(message)
    if target is None:
        return False
    return CommunicationOutbox.objects.filter(
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        status=CommunicationOutboxStatus.SENDING,
        **target,
    ).exists()


def has_open_appointment_google_work(appointment_id):
    """PENDING/FAILED (retryable) or SENDING Google rows for this appointment."""
    if has_in_flight_google_sync(appointment_id):
        return True
    return CommunicationOutbox.objects.filter(
        appointment_id=appointment_id,
        channel=CommunicationChannel.GOOGLE_CALENDAR,
        status__in=OPEN_GOOGLE_OUTBOX_STATUSES,
        attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
    ).exists()


def appointment_has_pending_whatsapp(appointment_id):
    return CommunicationOutbox.objects.filter(
        appointment_id=appointment_id,
        channel=CommunicationChannel.WHATSAPP,
        status__in=[
            CommunicationOutboxStatus.PENDING,
            CommunicationOutboxStatus.FAILED,
        ],
        attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
    ).exists()


LOCATION_WHATSAPP_EVENT_TYPES = frozenset(
    {
        CommunicationEventType.APPOINTMENT_CONFIRMED,
        CommunicationEventType.APPOINTMENT_RESCHEDULED,
    }
)


def should_defer_whatsapp_until_google_meet(message):
    """
    Confirm/reschedule virtual WA: hold only while Meet still missing and
    same-appointment Google work is open. Skip if Meet already on apt
    (e.g. reschedule) or event has no address/Meet slot (cancel).
    """
    if message.channel != CommunicationChannel.WHATSAPP:
        return False
    if message.appointment_id is None:
        return False
    if message.event_type not in LOCATION_WHATSAPP_EVENT_TYPES:
        return False
    appointment_row = (
        Appointment.objects.filter(pk=message.appointment_id)
        .values("modality", "google_meet_link")
        .first()
    )
    if appointment_row is None:
        return False
    if appointment_row["modality"] != AppointmentModes.VIRTUAL:
        return False
    if (appointment_row["google_meet_link"] or "").strip():
        return False
    return has_open_appointment_google_work(message.appointment_id)


def refresh_whatsapp_template_parameters(message):
    """Rebuild Meta body params from live appointment (Meet link after GC)."""
    if message.appointment_id is None:
        return message.template_parameters or []
    appointment = (
        Appointment.objects.filter(pk=message.appointment_id)
        .select_related("center", "service", "customer_profile")
        .first()
    )
    if appointment is None:
        return message.template_parameters or []
    parameters = build_template_parameters(message.event_type, appointment)
    if parameters != (message.template_parameters or []):
        message.template_parameters = parameters
        message.save(update_fields=["template_parameters", "updated_at"])
    return parameters


def remaining_google_outbox_work(appointment_id, exclude_message_id):
    return (
        CommunicationOutbox.objects.filter(
            appointment_id=appointment_id,
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            status__in=OPEN_GOOGLE_OUTBOX_STATUSES,
            attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
        )
        .exclude(pk=exclude_message_id)
        .exists()
    )


def remaining_google_outbox_work_for_message(message):
    target = google_outbox_target_filter_for_message(message)
    if target is None:
        return False
    return (
        CommunicationOutbox.objects.filter(
            channel=CommunicationChannel.GOOGLE_CALENDAR,
            status__in=OPEN_GOOGLE_OUTBOX_STATUSES,
            attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
            **target,
        )
        .exclude(pk=message.pk)
        .exists()
    )


def finish_google_outbox_message(message, result):
    if remaining_google_outbox_work_for_message(message):
        publish_outbox_wake()
        return result
    # After apt GC settles, wake so deferred virtual WA can send with Meet.
    if (
        message.appointment_id is not None
        and result is not None
        and result.status
        in (
            CommunicationOutboxStatus.ACCEPTED,
            CommunicationOutboxStatus.SKIPPED,
        )
        and appointment_has_pending_whatsapp(message.appointment_id)
    ):
        publish_outbox_wake()
    return result


def process_whatsapp_outbox_message(message):
    if not is_whatsapp_configured():
        return mark_outbox_skipped(message, "WhatsApp is not configured")
    if not message.to_phone:
        return mark_outbox_skipped(message, "Customer phone is missing")

    body_parameters = refresh_whatsapp_template_parameters(message)
    status_code, body = send_template(
        to_phone=message.to_phone,
        template_name=message.template_name,
        language_code=message.template_language,
        body_parameters=body_parameters,
    )
    if status_code < 300:
        return mark_outbox_accepted(
            message,
            wamid=extract_wamid(body) or "",
            provider_response=body,
        )

    error = {}
    if isinstance(body, dict):
        error = (body.get("error") or {}) if isinstance(body.get("error"), dict) else {}
    return mark_outbox_failed(
        message,
        error_code=error.get("code") or status_code,
        error_detail=error.get("message") or body,
        provider_response=body,
    )


RETRYABLE_GOOGLE_SKIP_REASONS = {
    "Google Calendar organizer is disconnected": "organizer_disconnected",
}


def run_google_outbox_desired_state(message):
    if message.appointment_id is not None:
        if not is_google_calendar_configured():
            return "Google Calendar is not configured"
        return sync_appointment_with_google(message.appointment_id)
    if message.availability_series_id is not None:
        return sync_associate_blocks_to_personal_google(
            series_id=message.availability_series_id
        )
    if message.associate_availability_block_id is not None:
        return sync_associate_blocks_to_personal_google(
            block_id=message.associate_availability_block_id
        )
    if message.associate_leave_id is not None:
        return sync_associate_leave_to_personal_google(message.associate_leave_id)
    return "Google Calendar outbox row has no sync target"


def process_google_outbox_message(message):
    try:
        skip_reason = run_google_outbox_desired_state(message)
    except GOOGLE_SYNC_ERRORS as error:
        return finish_google_outbox_message(
            message,
            mark_outbox_failed(
                message,
                error_code=type(error).__name__,
                error_detail=describe_google_error(error),
            ),
        )
    if not skip_reason:
        return finish_google_outbox_message(
            message, mark_outbox_accepted(message)
        )
    retry_code = RETRYABLE_GOOGLE_SKIP_REASONS.get(skip_reason)
    if retry_code:
        return finish_google_outbox_message(
            message,
            mark_outbox_failed(
                message,
                error_code=retry_code,
                error_detail=skip_reason,
            ),
        )
    return finish_google_outbox_message(
        message, mark_outbox_skipped(message, skip_reason)
    )


def process_unknown_channel_message(message):
    return mark_outbox_skipped(
        message, f"Unknown communication channel: {message.channel}"
    )


CHANNEL_PROCESSORS = {
    CommunicationChannel.WHATSAPP: process_whatsapp_outbox_message,
    CommunicationChannel.GOOGLE_CALENDAR: process_google_outbox_message,
}


def process_outbox_message(message_id):
    message = CommunicationOutbox.objects.filter(pk=message_id).first()
    if message is None:
        return None
    if message.status == CommunicationOutboxStatus.FAILED and (
        message.attempt_count >= MAX_OUTBOX_ATTEMPTS
    ):
        return mark_outbox_exhausted(message)
    if message.status not in (
        CommunicationOutboxStatus.PENDING,
        CommunicationOutboxStatus.FAILED,
    ):
        return message
    if (
        message.channel == CommunicationChannel.GOOGLE_CALENDAR
        and has_in_flight_google_sync_for_message(message)
    ):
        return message
    if should_defer_whatsapp_until_google_meet(message):
        return message

    claimed = claim_outbox_message(message_id)
    if claimed is None:
        return CommunicationOutbox.objects.filter(pk=message_id).first()
    processor = CHANNEL_PROCESSORS.get(
        claimed.channel, process_unknown_channel_message
    )
    return processor(claimed)


def process_pending_outbox(*, limit=50):
    reclaim_stale_sending_messages()
    pending_ids = list(
        CommunicationOutbox.objects.filter(
            status=CommunicationOutboxStatus.PENDING,
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    failed_ids = list(
        CommunicationOutbox.objects.filter(
            status=CommunicationOutboxStatus.FAILED,
            wamid="",
            attempt_count__lt=MAX_OUTBOX_ATTEMPTS,
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    results = []
    seen_ids = set()
    for message_id in list(pending_ids) + list(failed_ids):
        if message_id in seen_ids:
            continue
        seen_ids.add(message_id)
        results.append(process_outbox_message(message_id))
    return results


def apply_whatsapp_status_update(status_payload):
    wamid = status_payload.get("id") or ""
    provider_status = status_payload.get("status") or ""
    timestamp = str(status_payload.get("timestamp") or "")
    if not wamid or not provider_status:
        return None

    event_key = f"{wamid}:{provider_status}:{timestamp}"
    try:
        _event, created = CommunicationWebhookEvent.objects.get_or_create(
            event_key=event_key,
            defaults={
                "wamid": wamid,
                "status": provider_status,
                "payload": status_payload,
            },
        )
    except IntegrityError:
        # Concurrent duplicate webhook — treat as already processed.
        return None
    if not created:
        return None

    message = CommunicationOutbox.objects.filter(wamid=wamid).first()
    if message is None:
        return None

    mapped_status = WEBHOOK_STATUS_MAP.get(provider_status)
    if mapped_status is None:
        return message

    now = timezone.now()
    update_fields = ["updated_at"]

    if mapped_status == CommunicationOutboxStatus.FAILED:
        errors = status_payload.get("errors") or []
        error = errors[0] if errors else {}
        message.status = CommunicationOutboxStatus.FAILED
        message.failed_at = now
        message.error_code = str(error.get("code") or "")
        message.error_detail = str(
            (error.get("error_data") or {}).get("details")
            or error.get("message")
            or error.get("title")
            or ""
        )
        update_fields.extend(
            ["status", "failed_at", "error_code", "error_detail"]
        )
        message.save(update_fields=update_fields)
        return message

    current_rank = STATUS_RANK.get(message.status, 0)
    next_rank = STATUS_RANK.get(mapped_status, 0)
    if next_rank > current_rank:
        message.status = mapped_status
        update_fields.append("status")

    if mapped_status == CommunicationOutboxStatus.SENT and message.sent_at is None:
        message.sent_at = now
        update_fields.append("sent_at")

    if mapped_status in (
        CommunicationOutboxStatus.DELIVERED,
        CommunicationOutboxStatus.READ,
    ) and message.delivered_at is None:
        message.delivered_at = now
        update_fields.append("delivered_at")

    if mapped_status == CommunicationOutboxStatus.READ and message.read_at is None:
        message.read_at = now
        update_fields.append("read_at")

    message.save(update_fields=update_fields)
    return message


def process_whatsapp_webhook_payload(body):
    if not isinstance(body, dict):
        return
    if body.get("object") != "whatsapp_business_account":
        return
    for entry in body.get("entry") or []:
        for change in entry.get("changes") or []:
            if change.get("field") != "messages":
                continue
            value = change.get("value") or {}
            for status_payload in value.get("statuses") or []:
                apply_whatsapp_status_update(status_payload)
