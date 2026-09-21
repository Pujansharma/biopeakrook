from django.core.management.base import BaseCommand

from integrations.google_calendar.google_sync import GOOGLE_SYNC_ERRORS
from integrations.google_calendar.webhook_channel import (
    ensure_watch_channel_active,
    personal_connections_needing_watch_renewal,
)


class Command(BaseCommand):
    help = (
        "Renew personal Google Calendar notification channels that are "
        "close to expiring. Run this on the basis of expiry frequency."
    )

    def handle(self, *args, **options):
        renewed = 0
        failed = 0
        for connection in personal_connections_needing_watch_renewal():
            try:
                ensure_watch_channel_active(connection)
            except GOOGLE_SYNC_ERRORS as error:
                failed += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Failed to renew channel for user {connection.pk}: {error}"
                    )
                )
                continue
            renewed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Renewed {renewed} Google Calendar watch channel(s); {failed} failed."
            )
        )
