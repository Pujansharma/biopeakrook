from django.core.management.base import BaseCommand

from appointments.utils.exceptions import process_pending_exception_scans


class Command(BaseCommand):
    help = "Process pending appointment exception scan jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of jobs to process in one run.",
        )

    def handle(self, *args, **options):
        processed = process_pending_exception_scans(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} appointment exception scan job(s)."
            )
        )
