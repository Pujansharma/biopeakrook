from django.core.management.base import BaseCommand

from programs.models import Program
from programs.utils.helper import generate_program_unique_id


class Command(BaseCommand):
    help = "Backfill UIDs for programs that do not have one."

    def handle(self, *args, **options):
        programs = Program.objects.filter(uid__isnull=True)
        updated_count = 0

        for program in programs:
            program.uid = generate_program_unique_id()
            program.save(update_fields=["uid"])
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfilled UIDs for {updated_count} program(s)."
            )
        )
