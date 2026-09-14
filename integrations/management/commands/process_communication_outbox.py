from django.core.management.base import BaseCommand

from integrations.communications.outbox import process_pending_outbox


class Command(BaseCommand):
    help = (
        "Process pending / retryable communication outbox rows "
        "(WhatsApp + Google Calendar)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max outbox rows to process this run.",
        )

    def handle(self, *args, **options):
        results = process_pending_outbox(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"Processed {len(results)} communication outbox row(s).")
        )
