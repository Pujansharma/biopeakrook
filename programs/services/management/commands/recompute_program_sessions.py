from django.core.management.base import BaseCommand
from django.db.models import Count, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from programs.models import (
    Program,
    ProgramService,
    TherapyProgram,
    TherapyProgramService,
)


class Command(BaseCommand):
    help = "Recompute therapy session totals and program service cancellations."

    def handle(self, *args: object, **options: object) -> None:
        cancelled_services = TherapyProgramService.objects.filter(
            program_service__is_active=False
        ).update(sessions_cancelled=F("sessions_count") - F("sessions_used"))

        reset_services = TherapyProgramService.objects.filter(
            program_service__is_active=True
        ).update(sessions_cancelled=Value(0))

        sessions_count_subquery = Coalesce(
            Subquery(
                TherapyProgramService.objects.filter(
                    program_service__program=OuterRef("program")
                )
                .values("program_service__program")
                .annotate(total=Sum("sessions_count"))
                .values("total")
            ),
            Value(0),
        )
        sessions_used_subquery = Coalesce(
            Subquery(
                TherapyProgramService.objects.filter(
                    program_service__program=OuterRef("program")
                )
                .values("program_service__program")
                .annotate(total=Sum("sessions_used"))
                .values("total")
            ),
            Value(0),
        )
        sessions_cancelled_subquery = Coalesce(
            Subquery(
                TherapyProgramService.objects.filter(
                    program_service__program=OuterRef("program")
                )
                .values("program_service__program")
                .annotate(total=Sum("sessions_cancelled"))
                .values("total")
            ),
            Value(0),
        )
        services_cancelled_subquery = Coalesce(
            Subquery(
                ProgramService.objects.filter(program=OuterRef("pk"), is_active=False)
                .values("program")
                .annotate(count=Count("pk"))
                .values("count")
            ),
            Value(0),
        )

        updated_therapy_programs = TherapyProgram.objects.update(
            sessions_count=sessions_count_subquery,
            sessions_used=sessions_used_subquery,
            sessions_cancelled=sessions_cancelled_subquery,
        )

        updated_programs = Program.objects.update(
            services_cancelled=services_cancelled_subquery,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"ProgramService: {cancelled_services} cancelled, {reset_services} reset. "
                f"TherapyProgram: {updated_therapy_programs} session totals recomputed. "
                f"Program: {updated_programs} service cancellations recomputed."
            )
        )
