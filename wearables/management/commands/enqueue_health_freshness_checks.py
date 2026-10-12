from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.customers.models import CustomerProfile
from wearables.services.job_processor import (
    connections_requiring_recovery_pull,
    profiles_requiring_freshness_check,
)
from wearables.services.job_queue import enqueue_health_job
from wearables.utils.constants import HealthJobType


class Command(BaseCommand):
    help = "Enqueue dashboard freshness checks for active wearable profiles."

    def handle(self, *args, **options):
        if not getattr(settings, "WEARABLES_ENABLED", True):
            self.stdout.write("Wearable integration is disabled; no jobs enqueued.")
            return
        profile_ids = list(profiles_requiring_freshness_check())
        profiles = CustomerProfile.objects.filter(pk__in=profile_ids)
        date_key = timezone.localdate().isoformat()
        count = 0
        for customer_profile in profiles.iterator():
            enqueue_health_job(
                job_type=HealthJobType.FRESHNESS_CHECK,
                idempotency_key=f"freshness:{customer_profile.pk}:{date_key}",
                customer_profile=customer_profile,
            )
            count += 1
        recovery_count = 0
        for connection in connections_requiring_recovery_pull().iterator():
            enqueue_health_job(
                job_type=HealthJobType.RECOVERY_PULL,
                idempotency_key=f"recovery:{connection.pk}:{date_key}",
                customer_profile=connection.customer_profile,
                connection=connection,
            )
            recovery_count += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Enqueued {count} freshness check(s) and "
                f"{recovery_count} recovery pull(s)."
            )
        )

