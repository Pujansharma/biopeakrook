from django.core.management.base import BaseCommand
from django.db.models import Count, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from programs.models import Program, ProgramService


class Command(BaseCommand):
    help = "Recompute sessions_count, sessions_used, sessions_cancelled, and services_cancelled on Program and ProgramService."

    def handle(self, *args, **options):
        cancelled_services = ProgramService.objects.filter(is_active=False).update(
            sessions_cancelled=F("sessions_count") - F("sessions_used")
        )

        reset_services = ProgramService.objects.filter(is_active=True).update(
            sessions_cancelled=Value(0)
        )

        sessions_count_subquery = Coalesce(
            Subquery(
                ProgramService.objects.filter(program_id=OuterRef("pk"))
                .values("program_id")
                .annotate(total=Sum("sessions_count"))
                .values("total")
            ),
            Value(0),
        )
        sessions_used_subquery = Coalesce(
            Subquery(
                ProgramService.objects.filter(program_id=OuterRef("pk"))
                .values("program_id")
                .annotate(total=Sum("sessions_used"))
                .values("total")
            ),
            Value(0),
        )
        sessions_cancelled_subquery = Coalesce(
            Subquery(
                ProgramService.objects.filter(program_id=OuterRef("pk"))
                .values("program_id")
                .annotate(total=Sum("sessions_cancelled"))
                .values("total")
            ),
            Value(0),
        )
        services_cancelled_subquery = Coalesce(
            Subquery(
                ProgramService.objects.filter(
                    program_id=OuterRef("pk"), is_active=False
                )
                .values("program_id")
                .annotate(count=Count("pk"))
                .values("count")
            ),
            Value(0),
        )

        updated_programs = Program.objects.update(
            sessions_count=sessions_count_subquery,
            sessions_used=sessions_used_subquery,
            sessions_cancelled=sessions_cancelled_subquery,
            services_cancelled=services_cancelled_subquery,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"ProgramService: {cancelled_services} cancelled, {reset_services} reset. "
                f"Program: {updated_programs} recomputed."
            )
        )
