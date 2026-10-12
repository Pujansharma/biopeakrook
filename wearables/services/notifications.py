from django.db import transaction
from django.utils import timezone

from wearables.models import RookMemberIdentity, WearableConnection
from wearables.services.connections import record_connection_event
from wearables.services.job_queue import enqueue_health_job
from wearables.services.provenance import canonical_source
from wearables.utils.constants import (
    AuthorizationStatus,
    ConnectionStatus,
    HealthJobType,
    HistoricalImportStatus,
    PermissionStatus,
)


def notification_text(payload: dict) -> str:
    values = [
        payload.get("event"),
        payload.get("event_type"),
        payload.get("type"),
        payload.get("status"),
        payload.get("notification_type"),
        payload.get("message"),
    ]
    return (
        " ".join(str(value) for value in values if value)
        .lower()
        .replace("_", " ")
        .replace("-", " ")
    )


def notification_data_source(payload: dict) -> str:
    return canonical_source(
        payload.get("data_source")
        or payload.get("source")
        or payload.get("provider")
        or ""
    )


def apply_notification_state(connection: WearableConnection, text: str) -> None:
    if any(token in text for token in ("authorization expired", "token expired")):
        connection.status = ConnectionStatus.AUTHORIZATION_EXPIRED
        connection.authorization_status = AuthorizationStatus.EXPIRED
        return
    if any(token in text for token in ("disconnect", "deauthor", "revoked")):
        connection.status = ConnectionStatus.DISCONNECTED
        connection.authorization_status = AuthorizationStatus.REVOKED
        connection.disconnected_at = timezone.now()
        return
    if any(token in text for token in ("permission denied", "insufficient scope")):
        connection.status = ConnectionStatus.PERMISSION_DENIED
        connection.authorization_status = AuthorizationStatus.DENIED
        connection.permission_status = PermissionStatus.DENIED
        return
    if any(token in text for token in ("import started", "historical started")):
        connection.status = ConnectionStatus.IMPORTING
        connection.import_status = HistoricalImportStatus.RUNNING
        connection.import_started_at = timezone.now()
        return
    if any(token in text for token in ("import partial", "historical partial")):
        connection.status = ConnectionStatus.PARTIAL
        connection.import_status = HistoricalImportStatus.PARTIAL
        return
    if any(token in text for token in ("import failed", "historical failed")):
        connection.status = ConnectionStatus.PROVIDER_ERROR
        connection.import_status = HistoricalImportStatus.FAILED
        return
    if any(token in text for token in ("retrieval failed", "fetch failed", "error")):
        connection.status = ConnectionStatus.PROVIDER_ERROR
        return
    if any(
        token in text
        for token in (
            "connected",
            "authorized",
            "authorization completed",
            "import completed",
        )
    ):
        connection.status = ConnectionStatus.ACTIVE
        connection.authorization_status = AuthorizationStatus.AUTHORIZED
        connection.import_status = HistoricalImportStatus.COMPLETED
        connection.connected_at = connection.connected_at or timezone.now()


@transaction.atomic
def process_rook_notification(payload: dict) -> dict:
    rook_user_id = str(payload.get("user_id") or "")
    data_source = notification_data_source(payload)
    if not rook_user_id or not data_source:
        return {"accepted": True, "skipped": True, "reason": "missing_identity"}
    identity = RookMemberIdentity.objects.filter(rook_user_id=rook_user_id).first()
    if identity is None:
        return {"accepted": True, "skipped": True, "reason": "unknown_user"}
    connection = (
        WearableConnection.objects.select_for_update()
        .filter(
            customer_profile=identity.customer_profile,
            data_source=data_source,
        )
        .first()
    )
    if connection is None:
        return {"accepted": True, "skipped": True, "reason": "unknown_connection"}
    previous_status = connection.status
    text = notification_text(payload)
    apply_notification_state(connection, text)
    connection.last_webhook_received_at = timezone.now()
    if connection.status == ConnectionStatus.PROVIDER_ERROR:
        connection.last_error_code = "rook_notification"
        connection.last_error_detail = str(payload.get("message") or text)[:512]
    else:
        connection.last_error_code = ""
        connection.last_error_detail = ""
    connection.save()
    record_connection_event(
        connection,
        event_type="rook_notification",
        previous_status=previous_status,
        detail=text[:512],
        payload=payload,
    )
    if connection.status == ConnectionStatus.PROVIDER_ERROR:
        enqueue_health_job(
            job_type=HealthJobType.RECOVERY_PULL,
            idempotency_key=(
                f"notification-recovery:{connection.pk}:"
                f"{timezone.localdate().isoformat()}"
            ),
            customer_profile=connection.customer_profile,
            connection=connection,
        )
    return {
        "accepted": True,
        "connectionId": str(connection.pk),
        "status": connection.status,
    }

