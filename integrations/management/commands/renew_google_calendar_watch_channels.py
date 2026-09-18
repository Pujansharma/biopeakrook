from django.core.management.base import BaseCommand

from core.utils.log import logger
from integrations.google_calendar.google_sync import GOOGLE_SYNC_ERRORS
from integrations.google_calendar.webhook_channel import (
    ensure_watch_channel_active,
    google_calendar_webhook_configured,
    personal_connections_needing_watch_renewal,
)


class Command(BaseCommand):
    help = (
        "Renew personal Google Calendar notification channels that are "
        "missing or close to expiring. Run this on this basis of expiry frequency."
    )

    def handle(self, *args, **options):
        if not google_calendar_webhook_configured():
            self.stdout.write(
                self.style.WARNING(
                    "BE_SERVICE_BASE_URL is not set; skipping."
                )
            )
            return

        renewed = 0
        for connection in personal_connections_needing_watch_renewal():
            try:
                ensure_watch_channel_active(connection)
            except GOOGLE_SYNC_ERRORS as error:
                logger.warning(
                    f"Google Calendar watch: failed to renew channel for "
                    f"user {connection.pk}: {error}"
                )
                continue
            renewed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Renewed {renewed} Google Calendar watch channel(s)."
            )
        )
