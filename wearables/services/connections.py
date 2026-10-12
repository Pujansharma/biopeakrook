from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.customers.models import CustomerProfile
from wearables.models import (
    RookMemberIdentity,
    WearableConnection,
    WearableConnectionEvent,
)
from wearables.services.client import (
    RookClient,
    RookConfigurationError,
    RookServiceError,
)
from wearables.services.identity import (
    get_or_create_rook_identity,
    record_wearable_consent,
)
from wearables.services.job_queue import enqueue_health_job
from wearables.utils.constants import (
    API_WEARABLE_SOURCES,
    NATIVE_WEARABLE_SOURCES,
    AuthorizationStatus,
    ConnectionMethod,
    ConnectionStatus,
    HealthJobType,
    HistoricalImportStatus,
    PermissionStatus,
)


def connection_method_for_source(data_source: str) -> str:
    if data_source in NATIVE_WEARABLE_SOURCES:
        return ConnectionMethod.SDK
    return ConnectionMethod.API


def record_connection_event(
    connection: WearableConnection,
    *,
    event_type: str,
    previous_status: str,
    actor_user=None,
    correlation_id: str = "",
    detail: str = "",
    payload: dict | None = None,
) -> WearableConnectionEvent:
    return WearableConnectionEvent.objects.create(
        connection=connection,
        event_type=event_type,
        previous_status=previous_status,
        current_status=connection.status,
        actor_user=actor_user,
        correlation_id=correlation_id,
        detail=detail[:512],
        payload=payload or {},
    )


def save_connection_transition(
    connection: WearableConnection,
    *,
    status: str,
    authorization_status: str | None = None,
    permission_status: str | None = None,
    import_status: str | None = None,
    actor_user=None,
    event_type: str,
    correlation_id: str = "",
    detail: str = "",
    payload: dict | None = None,
) -> WearableConnection:
    previous_status = connection.status
    connection.status = status
    update_fields = ["status", "updated_at"]
    optional_values = {
        "authorization_status": authorization_status,
        "permission_status": permission_status,
        "import_status": import_status,
    }
    for field_name, value in optional_values.items():
        if value is not None:
            setattr(connection, field_name, value)
            update_fields.append(field_name)
    connection.save(update_fields=update_fields)
    record_connection_event(
        connection,
        event_type=event_type,
        previous_status=previous_status,
        actor_user=actor_user,
        correlation_id=correlation_id,
        detail=detail,
        payload=payload,
    )
    return connection


def get_or_create_connection(
    *,
    customer_profile: CustomerProfile,
    identity: RookMemberIdentity,
    data_source: str,
    historical_days_requested: int | None,
) -> WearableConnection:
    requested_days = (
        historical_days_requested
        if historical_days_requested is not None
        else getattr(settings, "ROOK_HISTORICAL_DAYS", 29)
    )
    connection, created = WearableConnection.objects.get_or_create(
        customer_profile=customer_profile,
        data_source=data_source,
        defaults={
            "identity": identity,
            "connection_method": connection_method_for_source(data_source),
            "historical_days_requested": requested_days,
        },
    )
    update_fields = []
    if connection.identity_id != identity.pk:
        connection.identity = identity
        update_fields.append("identity")
    if (
        historical_days_requested is not None
        and connection.historical_days_requested != historical_days_requested
    ):
        connection.historical_days_requested = historical_days_requested
        update_fields.append("historical_days_requested")
    if update_fields and not created:
        update_fields.append("updated_at")
        connection.save(update_fields=update_fields)
    return connection


@transaction.atomic
def prepare_connection(
    *,
    request,
    customer_profile: CustomerProfile,
    data_source: str,
    consent_version: str,
    historical_days_requested: int,
    timezone_name: str | None,
    preferred_units: str | None,
) -> WearableConnection:
    identity = get_or_create_rook_identity(
        customer_profile,
        timezone_name=timezone_name,
        preferred_units=preferred_units,
    )
    record_wearable_consent(
        request=request,
        customer_profile=customer_profile,
        consent_version=consent_version,
    )
    return get_or_create_connection(
        customer_profile=customer_profile,
        identity=identity,
        data_source=data_source,
        historical_days_requested=historical_days_requested,
    )


def start_connection(
    *,
    request,
    customer_profile: CustomerProfile,
    validated_data: dict,
    correlation_id: str = "",
) -> dict:
    data_source = validated_data["data_source"]
    connection = prepare_connection(
        request=request,
        customer_profile=customer_profile,
        data_source=data_source,
        consent_version=validated_data["consent_version"],
        historical_days_requested=validated_data["historical_days"],
        timezone_name=validated_data.get("timezone_name"),
        preferred_units=validated_data.get("preferred_units"),
    )
    now = timezone.now()
    connection.last_error_code = ""
    connection.last_error_detail = ""
    connection.disconnected_at = None
    connection.import_completed_at = None
    connection.save(
        update_fields=[
            "last_error_code",
            "last_error_detail",
            "disconnected_at",
            "import_completed_at",
            "updated_at",
        ]
    )
    if data_source in NATIVE_WEARABLE_SOURCES:
        save_connection_transition(
            connection,
            status=ConnectionStatus.CONNECTING,
            authorization_status=AuthorizationStatus.PENDING,
            permission_status=PermissionStatus.NOT_DETERMINED,
            import_status=HistoricalImportStatus.NOT_STARTED,
            actor_user=request.user,
            event_type="connection_requested",
            correlation_id=correlation_id,
            detail="Native SDK authorization requested.",
        )
        return {
            "connection": connection,
            "authorization_method": ConnectionMethod.SDK,
            "authorization_url": None,
        }

    client = RookClient()
    try:
        result = client.get_authorizer(
            rook_user_id=connection.identity.rook_user_id,
            data_source=data_source,
            redirect_url=validated_data.get("redirect_url"),
        )
    except (RookConfigurationError, RookServiceError) as error:
        connection.last_error_code = "rook_authorizer_failed"
        connection.last_error_detail = str(error)[:512]
        connection.save(
            update_fields=["last_error_code", "last_error_detail", "updated_at"]
        )
        save_connection_transition(
            connection,
            status=ConnectionStatus.PROVIDER_ERROR,
            authorization_status=AuthorizationStatus.ERROR,
            actor_user=request.user,
            event_type="authorization_failed",
            correlation_id=correlation_id,
            detail=str(error),
        )
        raise
    authorized = result["authorized"]
    connection.connected_at = connection.connected_at or (now if authorized else None)
    connection.import_started_at = now if authorized else connection.import_started_at
    connection.save(update_fields=["connected_at", "import_started_at", "updated_at"])
    save_connection_transition(
        connection,
        status=(ConnectionStatus.IMPORTING if authorized else ConnectionStatus.AUTHORIZING),
        authorization_status=(
            AuthorizationStatus.AUTHORIZED if authorized else AuthorizationStatus.PENDING
        ),
        import_status=(
            HistoricalImportStatus.RUNNING
            if authorized
            else HistoricalImportStatus.NOT_STARTED
        ),
        actor_user=request.user,
        event_type="authorization_confirmed" if authorized else "authorization_started",
        correlation_id=correlation_id,
    )
    if authorized:
        enqueue_health_job(
            job_type=HealthJobType.RECOVERY_PULL,
            idempotency_key=(
                f"connection-recovery:{connection.pk}:"
                f"{timezone.localdate().isoformat()}"
            ),
            customer_profile=customer_profile,
            connection=connection,
        )
    return {
        "connection": connection,
        "authorization_method": ConnectionMethod.API,
        "authorization_url": result["authorization_url"],
    }


def refresh_authorizing_connections(customer_profile: CustomerProfile) -> None:
    connections = list(
        WearableConnection.objects.select_related("identity").filter(
            customer_profile=customer_profile,
            connection_method=ConnectionMethod.API,
            status__in=[ConnectionStatus.CONNECTING, ConnectionStatus.AUTHORIZING],
        )
    )
    if not connections:
        return
    authorized_sources = RookClient().get_authorized_sources(
        rook_user_id=connections[0].identity.rook_user_id
    )
    now = timezone.now()
    for connection in connections:
        if connection.data_source not in authorized_sources:
            continue
        connection.connected_at = connection.connected_at or now
        connection.import_started_at = connection.import_started_at or now
        connection.save(
            update_fields=["connected_at", "import_started_at", "updated_at"]
        )
        save_connection_transition(
            connection,
            status=ConnectionStatus.IMPORTING,
            authorization_status=AuthorizationStatus.AUTHORIZED,
            import_status=HistoricalImportStatus.RUNNING,
            event_type="authorization_confirmed",
        )
        enqueue_health_job(
            job_type=HealthJobType.RECOVERY_PULL,
            idempotency_key=(
                f"authorization-recovery:{connection.pk}:"
                f"{timezone.localdate().isoformat()}"
            ),
            customer_profile=customer_profile,
            connection=connection,
        )


def disconnect_connection(
    *,
    customer_profile: CustomerProfile,
    data_source: str,
    actor_user,
    correlation_id: str = "",
) -> tuple[WearableConnection | None, bool]:
    connection = (
        WearableConnection.objects.select_related("identity")
        .filter(customer_profile=customer_profile, data_source=data_source)
        .first()
    )
    if connection is None:
        return None, False
    revoke_pending = False
    if connection.data_source in API_WEARABLE_SOURCES:
        try:
            RookClient().revoke_source(
                rook_user_id=connection.identity.rook_user_id,
                data_source=connection.data_source,
            )
        except (RookConfigurationError, RookServiceError) as error:
            revoke_pending = True
            connection.last_error_code = "revoke_pending"
            connection.last_error_detail = str(error)[:512]
            connection.save(
                update_fields=["last_error_code", "last_error_detail", "updated_at"]
            )
            enqueue_health_job(
                job_type=HealthJobType.REVOKE_CONNECTION,
                idempotency_key=f"revoke:{connection.pk}:{timezone.now().timestamp()}",
                customer_profile=customer_profile,
                connection=connection,
            )
    connection.disconnected_at = timezone.now()
    connection.save(update_fields=["disconnected_at", "updated_at"])
    save_connection_transition(
        connection,
        status=ConnectionStatus.DISCONNECTED,
        authorization_status=AuthorizationStatus.REVOKED,
        permission_status=PermissionStatus.UNKNOWN,
        actor_user=actor_user,
        event_type="connection_revoked",
        correlation_id=correlation_id,
        detail="Historical health data retained.",
        payload={"revoke_pending": revoke_pending},
    )
    return connection, revoke_pending


def update_native_connection(
    *,
    customer_profile: CustomerProfile,
    actor_user,
    validated_data: dict,
    correlation_id: str = "",
) -> WearableConnection:
    existing_connection = WearableConnection.objects.filter(
        customer_profile=customer_profile,
        data_source=validated_data["data_source"],
        connection_method=ConnectionMethod.SDK,
    ).first()
    if existing_connection is None:
        raise ValueError("Start the native wearable connection before reporting status.")
    identity = get_or_create_rook_identity(
        customer_profile,
        timezone_name=validated_data.get("timezone_name"),
    )
    connection = get_or_create_connection(
        customer_profile=customer_profile,
        identity=identity,
        data_source=validated_data["data_source"],
        historical_days_requested=validated_data.get(
            "historical_days",
            getattr(settings, "ROOK_HISTORICAL_DAYS", 29),
        ),
    )
    permission_status = validated_data["permission_status"]
    sdk_linked = validated_data["sdk_linked"]
    connection.capabilities = validated_data.get("capabilities", [])
    connection.last_error_code = ""
    connection.last_error_detail = ""
    connection.save(
        update_fields=[
            "capabilities",
            "last_error_code",
            "last_error_detail",
            "updated_at",
        ]
    )
    status = ConnectionStatus.CONNECTING
    authorization_status = AuthorizationStatus.PENDING
    import_status = HistoricalImportStatus.NOT_STARTED
    event_type = "native_status_updated"
    if permission_status == PermissionStatus.DENIED:
        status = ConnectionStatus.PERMISSION_DENIED
        authorization_status = AuthorizationStatus.DENIED
    elif sdk_linked and permission_status in {
        PermissionStatus.GRANTED,
        PermissionStatus.LIMITED,
    }:
        status = ConnectionStatus.IMPORTING
        authorization_status = AuthorizationStatus.AUTHORIZED
        import_status = HistoricalImportStatus.RUNNING
        now = timezone.now()
        connection.connected_at = connection.connected_at or now
        connection.import_started_at = connection.import_started_at or now
        connection.save(
            update_fields=["connected_at", "import_started_at", "updated_at"]
        )
        event_type = "native_authorization_confirmed"
    return save_connection_transition(
        connection,
        status=status,
        authorization_status=authorization_status,
        permission_status=permission_status,
        import_status=import_status,
        actor_user=actor_user,
        event_type=event_type,
        correlation_id=correlation_id,
    )


def connection_experience_state(connection: WearableConnection) -> str:
    if (
        connection.status in {ConnectionStatus.ACTIVE, ConnectionStatus.IDLE}
        and connection.last_successful_sync
        and connection.last_successful_sync
        < timezone.now()
        - timedelta(hours=getattr(settings, "ROOK_SYNC_DELAY_HOURS", 48))
    ):
        return "sync_delayed"
    return connection.status


def connection_actions(connection: WearableConnection) -> list[dict]:
    status = connection_experience_state(connection)
    action_map = {
        ConnectionStatus.PERMISSION_DENIED: [
            {"id": "grant_permission", "label": "Grant Permission"}
        ],
        ConnectionStatus.AUTHORIZATION_EXPIRED: [
            {"id": "reconnect", "label": "Reconnect"}
        ],
        ConnectionStatus.DISCONNECTED: [
            {"id": "reconnect", "label": "Reconnect"}
        ],
        ConnectionStatus.PROVIDER_ERROR: [
            {"id": "retry_sync", "label": "Retry Sync"}
        ],
        "sync_delayed": [{"id": "retry_sync", "label": "Retry Sync"}],
    }
    return action_map.get(status, [])


def serialize_connection(connection: WearableConnection) -> dict:
    return {
        "id": str(connection.pk),
        "provider": connection.data_source,
        "connectionMethod": connection.connection_method,
        "status": connection.status,
        "experienceState": connection_experience_state(connection),
        "authorizationStatus": connection.authorization_status,
        "permissionStatus": connection.permission_status,
        "importStatus": connection.import_status,
        "capabilities": connection.capabilities,
        "connectedAt": connection.connected_at,
        "disconnectedAt": connection.disconnected_at,
        "lastSuccessfulSync": connection.last_successful_sync,
        "lastWebhookReceivedAt": connection.last_webhook_received_at,
        "historicalDaysRequested": connection.historical_days_requested,
        "availableFrom": connection.available_from,
        "availableTo": connection.available_to,
        "lastError": (
            {
                "code": connection.last_error_code,
                "detail": connection.last_error_detail,
            }
            if connection.last_error_code
            else None
        ),
        "actions": connection_actions(connection),
    }
