from django.conf import settings
from django.core.management.base import BaseCommand

from wearables.services.job_processor import process_pending_health_jobs


class Command(BaseCommand):
    help = "Process pending and retryable wearable health jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum health jobs to process in this run.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "WEARABLES_ENABLED", True):
            self.stdout.write("Wearable integration is disabled; no jobs processed.")
            return
        results = process_pending_health_jobs(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"Processed {len(results)} wearable health job(s).")
        )

