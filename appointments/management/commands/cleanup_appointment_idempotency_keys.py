from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import AppointmentIdempotencyKey


class Command(BaseCommand):
    help = "Delete expired appointment idempotency keys."

    def handle(self, *args, **options):
        deleted_count, _ = AppointmentIdempotencyKey.objects.filter(
            expires_at__lt=timezone.now(),
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} expired appointment idempotency key(s)."
            )
        )
