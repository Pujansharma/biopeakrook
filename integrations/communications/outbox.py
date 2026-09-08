from django.db import transaction
from django.utils import timezone

from core.utils.log import logger
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
from integrations.models import CommunicationOutbox, CommunicationWebhookEvent
from integrations.utils.constants import (
    CommunicationChannel,
    CommunicationEventType,
    CommunicationOutboxStatus,
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


def enqueue_appointment_message(
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

    if not is_whatsapp_configured():
        return CommunicationOutbox.objects.create(
            appointment=appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=event_type,
            to_phone=to_phone,
            template_name=template_name or "",
            template_language=language,
            template_parameters=parameters,
            status=CommunicationOutboxStatus.SKIPPED,
            skip_reason="WhatsApp is not configured",
        )

    if not to_phone:
        return CommunicationOutbox.objects.create(
            appointment=appointment,
            channel=CommunicationChannel.WHATSAPP,
            event_type=event_type,
            to_phone="",
            template_name=template_name or "",
            template_language=language,
            template_parameters=parameters,
            status=CommunicationOutboxStatus.SKIPPED,
            skip_reason="Customer phone is missing",
        )

    if event_type in (
        CommunicationEventType.APPOINTMENT_CONFIRMED,
        CommunicationEventType.APPOINTMENT_CANCELLED,
    ):
        existing = (
            CommunicationOutbox.objects.filter(
                appointment=appointment,
                event_type=event_type,
            )
            .exclude(
                status__in=[
                    CommunicationOutboxStatus.SKIPPED,
                    CommunicationOutboxStatus.FAILED,
                ]
            )
            .first()
        )
        if existing:
            return existing

    message = CommunicationOutbox.objects.create(
        appointment=appointment,
        channel=CommunicationChannel.WHATSAPP,
        event_type=event_type,
        to_phone=to_phone,
        template_name=template_name,
        template_language=language,
        template_parameters=parameters,
        status=CommunicationOutboxStatus.PENDING,
    )
    message_id = message.pk
    transaction.on_commit(lambda: process_outbox_message(message_id))
    return message


def process_outbox_message(message_id):
    message = CommunicationOutbox.objects.filter(pk=message_id).first()
    if message is None:
        return None
    if message.status not in (
        CommunicationOutboxStatus.PENDING,
        CommunicationOutboxStatus.FAILED,
    ):
        return message
    if not is_whatsapp_configured():
        message.status = CommunicationOutboxStatus.SKIPPED
        message.skip_reason = "WhatsApp is not configured"
        message.save(update_fields=["status", "skip_reason", "updated_at"])
        return message
    if not message.to_phone:
        message.status = CommunicationOutboxStatus.SKIPPED
        message.skip_reason = "Customer phone is missing"
        message.save(update_fields=["status", "skip_reason", "updated_at"])
        return message

    message.status = CommunicationOutboxStatus.SENDING
    message.attempt_count = message.attempt_count + 1
    message.save(update_fields=["status", "attempt_count", "updated_at"])

    status_code, body = send_template(
        to_phone=message.to_phone,
        template_name=message.template_name,
        language_code=message.template_language,
        body_parameters=message.template_parameters or [],
    )
    message.provider_response = body
    wamid = extract_wamid(body)
    now = timezone.now()
    if status_code < 300 and wamid:
        message.wamid = wamid
        message.status = CommunicationOutboxStatus.ACCEPTED
        message.accepted_at = now
        message.error_code = ""
        message.error_detail = ""
        message.save(
            update_fields=[
                "wamid",
                "status",
                "accepted_at",
                "error_code",
                "error_detail",
                "provider_response",
                "updated_at",
            ]
        )
        return message

    error = {}
    if isinstance(body, dict):
        error = (body.get("error") or {}) if isinstance(body.get("error"), dict) else {}
    message.status = CommunicationOutboxStatus.FAILED
    message.failed_at = now
    message.error_code = str(error.get("code") or status_code)
    message.error_detail = str(error.get("message") or body)
    message.save(
        update_fields=[
            "status",
            "failed_at",
            "error_code",
            "error_detail",
            "provider_response",
            "updated_at",
        ]
    )
    logger.warning(
        f"WhatsApp outbox {message.pk} failed: {message.error_code} {message.error_detail}"
    )
    return message


def process_pending_outbox(*, limit=50):
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
        )
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    results = []
    for message_id in list(pending_ids) + list(failed_ids):
        results.append(process_outbox_message(message_id))
    return results


def apply_whatsapp_status_update(status_payload):
    wamid = status_payload.get("id") or ""
    provider_status = status_payload.get("status") or ""
    timestamp = str(status_payload.get("timestamp") or "")
    if not wamid or not provider_status:
        return None

    event_key = f"{wamid}:{provider_status}:{timestamp}"
    if CommunicationWebhookEvent.objects.filter(event_key=event_key).exists():
        return None

    CommunicationWebhookEvent.objects.create(
        event_key=event_key,
        wamid=wamid,
        status=provider_status,
        payload=status_payload,
    )

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
    ):
        if message.delivered_at is None:
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
