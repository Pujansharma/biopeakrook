from datetime import timedelta

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from wearables.models import HealthProcessingJob, WearableConnection
from wearables.services.analytics import refresh_profile_snapshots
from wearables.services.client import (
    RookClient,
    RookConfigurationError,
    RookServiceError,
)
from wearables.services.connections import refresh_authorizing_connections
from wearables.services.ingestion import ingest_rook_document, normalize_health_document
from wearables.utils.constants import (
    AuthorizationStatus,
    ConnectionMethod,
    ConnectionStatus,
    HealthJobStatus,
    HealthJobType,
    HistoricalImportStatus,
)

MAXIMUM_JOB_ATTEMPTS = 3
STALE_JOB_MINUTES = 15


def process_normalize_document(job: HealthProcessingJob) -> dict:
    if job.document_id is None:
        raise ValueError("Normalize job has no document.")
    return normalize_health_document(job.document_id)


def process_refresh_analytics(job: HealthProcessingJob) -> dict:
    if job.customer_profile_id is None:
        raise ValueError("Analytics job has no customer profile.")
    cards = refresh_profile_snapshots(job.customer_profile)
    return {"cardCount": len(cards)}


def process_refresh_connection(job: HealthProcessingJob) -> dict:
    if job.customer_profile_id is None:
        raise ValueError("Connection refresh job has no customer profile.")
    refresh_authorizing_connections(job.customer_profile)
    return {"refreshed": True}


def process_revoke_connection(job: HealthProcessingJob) -> dict:
    if job.connection_id is None:
        raise ValueError("Revoke job has no connection.")
    connection = WearableConnection.objects.select_related("identity").get(
        pk=job.connection_id
    )
    RookClient().revoke_source(
        rook_user_id=connection.identity.rook_user_id,
        data_source=connection.data_source,
    )
    connection.last_error_code = ""
    connection.last_error_detail = ""
    connection.save(
        update_fields=["last_error_code", "last_error_detail", "updated_at"]
    )
    return {"revoked": True}


def recovery_document(
    *,
    document: dict,
    rook_user_id: str,
    health_pillar: str,
    summary_date: str,
) -> dict:
    return {
        **document,
        "user_id": rook_user_id,
        "data_structure": document.get("data_structure")
        or f"{health_pillar}_health_summary",
        "datetime": document.get("datetime")
        or f"{summary_date}T00:00:00+00:00",
    }


def process_recovery_pull(job: HealthProcessingJob) -> dict:
    if job.connection_id is None:
        raise ValueError("Recovery pull job has no connection.")
    connection = WearableConnection.objects.select_related("identity").get(
        pk=job.connection_id
    )
    if connection.status == ConnectionStatus.DISCONNECTED:
        return {"skipped": True, "reason": "connection_disconnected"}
    client = RookClient()
    imported_count = 0
    error_count = 0
    today = timezone.localdate()
    for day_offset in range(7):
        summary_date = (today - timedelta(days=day_offset)).isoformat()
        for health_pillar in ("physical", "sleep", "body"):
            try:
                documents = client.get_processed_summaries(
                    rook_user_id=connection.identity.rook_user_id,
                    health_pillar=health_pillar,
                    summary_date=summary_date,
                )
            except RookServiceError:
                error_count += 1
                continue
            for document in documents:
                result = ingest_rook_document(
                    recovery_document(
                        document=document,
                        rook_user_id=connection.identity.rook_user_id,
                        health_pillar=health_pillar,
                        summary_date=summary_date,
                    ),
                    signature_valid=True,
                )
                imported_count += int(result.get("queued", False))
    if error_count == 21:
        connection.status = ConnectionStatus.PROVIDER_ERROR
        connection.import_status = HistoricalImportStatus.FAILED
        connection.last_error_code = "recovery_unavailable"
        connection.last_error_detail = (
            "All 21 recovery requests were unavailable. Stored history is safe."
        )
        connection.save(
            update_fields=[
                "status",
                "import_status",
                "last_error_code",
                "last_error_detail",
                "updated_at",
            ]
        )
        raise RookServiceError(
            "ROOK recovery data was unavailable. Stored health history is safe."
        )
    connection.authorization_status = AuthorizationStatus.AUTHORIZED
    connection.last_successful_sync = timezone.now()
    if error_count:
        connection.status = ConnectionStatus.PARTIAL
        connection.import_status = HistoricalImportStatus.PARTIAL
        connection.last_error_code = "recovery_partial"
        connection.last_error_detail = (
            f"{error_count} of 21 recovery requests were unavailable."
        )
    else:
        connection.status = (
            ConnectionStatus.ACTIVE if imported_count else ConnectionStatus.IDLE
        )
        connection.import_status = HistoricalImportStatus.COMPLETED
        connection.last_error_code = ""
        connection.last_error_detail = ""
        connection.import_completed_at = timezone.now()
    connection.save(
        update_fields=[
            "authorization_status",
            "last_successful_sync",
            "status",
            "import_status",
            "last_error_code",
            "last_error_detail",
            "import_completed_at",
            "updated_at",
        ]
    )
    return {
        "importedDocumentCount": imported_count,
        "partial": error_count > 0,
        "errorCount": error_count,
    }


def process_freshness_check(job: HealthProcessingJob) -> dict:
    if job.customer_profile_id is None:
        raise ValueError("Freshness job has no customer profile.")
    refresh_profile_snapshots(job.customer_profile)
    return {"refreshed": True}


JOB_HANDLERS = {
    HealthJobType.NORMALIZE_DOCUMENT: process_normalize_document,
    HealthJobType.REFRESH_ANALYTICS: process_refresh_analytics,
    HealthJobType.REFRESH_CONNECTION: process_refresh_connection,
    HealthJobType.REVOKE_CONNECTION: process_revoke_connection,
    HealthJobType.RECOVERY_PULL: process_recovery_pull,
    HealthJobType.FRESHNESS_CHECK: process_freshness_check,
}


def reset_stale_health_jobs() -> int:
    stale_before = timezone.now() - timedelta(minutes=STALE_JOB_MINUTES)
    return HealthProcessingJob.objects.filter(
        status=HealthJobStatus.RUNNING,
        locked_at__lt=stale_before,
    ).update(
        status=HealthJobStatus.FAILED,
        failure_detail="Worker lease expired.",
        scheduled_at=timezone.now(),
        locked_at=None,
        updated_at=timezone.now(),
    )


def claim_health_job(job_id) -> HealthProcessingJob | None:
    now = timezone.now()
    updated = HealthProcessingJob.objects.filter(
        pk=job_id,
        status__in=[HealthJobStatus.PENDING, HealthJobStatus.FAILED],
        scheduled_at__lte=now,
        attempt_count__lt=MAXIMUM_JOB_ATTEMPTS,
    ).update(
        status=HealthJobStatus.RUNNING,
        started_at=now,
        locked_at=now,
        attempt_count=F("attempt_count") + 1,
        failure_detail="",
        updated_at=now,
    )
    if not updated:
        return None
    return HealthProcessingJob.objects.select_related(
        "customer_profile",
        "document",
        "connection__identity",
    ).get(pk=job_id)


def complete_health_job(job: HealthProcessingJob, result: dict) -> None:
    HealthProcessingJob.objects.filter(pk=job.pk).update(
        status=HealthJobStatus.COMPLETED,
        payload={**job.payload, "result": result},
        completed_at=timezone.now(),
        locked_at=None,
        updated_at=timezone.now(),
    )


def fail_health_job(job: HealthProcessingJob, error: Exception) -> None:
    retry_delay = timedelta(minutes=5 * max(job.attempt_count, 1))
    HealthProcessingJob.objects.filter(pk=job.pk).update(
        status=HealthJobStatus.FAILED,
        failure_detail=str(error)[:512],
        scheduled_at=timezone.now() + retry_delay,
        locked_at=None,
        updated_at=timezone.now(),
    )


def process_health_job(job: HealthProcessingJob) -> dict:
    handler = JOB_HANDLERS.get(job.job_type)
    if handler is None:
        raise ValueError(f"Unsupported health job type: {job.job_type}")
    return handler(job)


def process_pending_health_jobs(*, limit: int = 50) -> list[dict]:
    reset_stale_health_jobs()
    job_ids = list(
        HealthProcessingJob.objects.filter(
            status__in=[HealthJobStatus.PENDING, HealthJobStatus.FAILED],
            scheduled_at__lte=timezone.now(),
            attempt_count__lt=MAXIMUM_JOB_ATTEMPTS,
        )
        .order_by("scheduled_at")
        .values_list("pk", flat=True)[:limit]
    )
    results = []
    handled_errors = (
        RookServiceError,
        RookConfigurationError,
        ValueError,
        WearableConnection.DoesNotExist,
    )
    for job_id in job_ids:
        job = claim_health_job(job_id)
        if job is None:
            continue
        try:
            result = process_health_job(job)
        except handled_errors as error:
            fail_health_job(job, error)
            results.append(
                {"jobId": str(job.pk), "status": "failed", "detail": str(error)}
            )
            continue
        complete_health_job(job, result)
        results.append({"jobId": str(job.pk), "status": "completed", **result})
    return results


def profiles_requiring_freshness_check():
    return (
        WearableConnection.objects.filter(
            status__in=[
                ConnectionStatus.ACTIVE,
                ConnectionStatus.IDLE,
                ConnectionStatus.PARTIAL,
            ]
        )
        .values_list("customer_profile_id", flat=True)
        .distinct()
    )


def connections_requiring_recovery_pull():
    delayed_before = timezone.now() - timedelta(
        hours=getattr(settings, "ROOK_SYNC_DELAY_HOURS", 48)
    )
    return WearableConnection.objects.filter(
        status__in=[
            ConnectionStatus.ACTIVE,
            ConnectionStatus.IDLE,
            ConnectionStatus.PARTIAL,
            ConnectionStatus.PROVIDER_ERROR,
        ],
        connection_method=ConnectionMethod.API,
    ).filter(
        Q(last_successful_sync__isnull=True)
        | Q(last_successful_sync__lt=delayed_before)
    )

