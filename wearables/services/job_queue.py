from django.utils import timezone

from wearables.models import (
    HealthProcessingJob,
    RookHealthDocument,
    WearableConnection,
)
from wearables.utils.constants import HealthJobStatus


def enqueue_health_job(
    *,
    job_type: str,
    idempotency_key: str,
    customer_profile=None,
    document: RookHealthDocument | None = None,
    connection: WearableConnection | None = None,
    payload: dict | None = None,
) -> HealthProcessingJob:
    job, _ = HealthProcessingJob.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "customer_profile": customer_profile,
            "document": document,
            "connection": connection,
            "job_type": job_type,
            "status": HealthJobStatus.PENDING,
            "payload": payload or {},
            "scheduled_at": timezone.now(),
        },
    )
    return job

