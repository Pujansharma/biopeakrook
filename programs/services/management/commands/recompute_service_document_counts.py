from django.core.management.base import BaseCommand
from django.db import transaction

from programs.program_services.utils.db import (
    update_all_program_service_document_counts,
    update_all_program_service_results_count,
    update_all_result_documents_count,
)


class Command(BaseCommand):
    help = (
        "Recompute stored result and document counts on program services and "
        "service results."
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            updated_result_count = update_all_result_documents_count()
            updated_program_service_results_count = (
                update_all_program_service_results_count()
            )
            updated_program_service_document_counts = (
                update_all_program_service_document_counts()
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed document counts for {updated_result_count} "
                f"service result(s), result counts for "
                f"{updated_program_service_results_count} program service(s), "
                f"and document, report, and raw data counts for "
                f"{updated_program_service_document_counts} program service(s)."
            )
        )
