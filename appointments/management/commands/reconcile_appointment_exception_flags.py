from django.core.management.base import BaseCommand

from appointments.models import Appointment
from appointments.utils.exceptions import recompute_appointment_exception_flag


class Command(BaseCommand):
    help = "Reconcile appointment has_open_exception flags with open exception rows."

    def handle(self, *args, **options):
        updated = 0
        for appointment in Appointment.objects.iterator():
            previous = appointment.has_open_exception
            current = recompute_appointment_exception_flag(appointment)
            if previous != current:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled has_open_exception for {updated} appointment(s)."
            )
        )
