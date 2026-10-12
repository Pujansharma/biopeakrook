from django.core.management.base import BaseCommand

from integrations.communications.service import (
    REMINDER_ENQUEUE_LIMIT,
    enqueue_due_appointment_reminders,
)
from integrations.utils.constants import CommunicationOutboxStatus


class Command(BaseCommand):
    help = (
        "Enqueue WhatsApp appointment reminders for confirmed appointments "
        "starting within the next hour. Does not wake SQS — run "
        "process_communication_outbox in the same sweep to send."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=REMINDER_ENQUEUE_LIMIT,
            help=f"Max reminder rows to enqueue this run (default {REMINDER_ENQUEUE_LIMIT}).",
        )

    def handle(self, *args, **options):
        messages = enqueue_due_appointment_reminders(limit=options["limit"])
        pending_count = sum(
            1
            for message in messages
            if message.status
            in {
                CommunicationOutboxStatus.PENDING,
                CommunicationOutboxStatus.FAILED,
            }
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Enqueued {len(messages)} reminder row(s) "
                f"({pending_count} pending/failed)."
            )
        )
