from django.core.management.base import BaseCommand
from django.db import transaction

from programs.composites.utils.db import (
    update_all_composite_program_document_counts,
    update_all_composite_program_results_count,
)
from programs.program_services.utils.db import (
    update_all_program_service_document_counts,
    update_all_program_service_fetch_counts,
    update_all_program_service_results_count,
    update_all_result_documents_count,
)


class Command(BaseCommand):
    help = (
        "Recompute stored fetch, result, and document counts on composite "
        "programs, program services, and service results."
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
            updated_program_service_fetch_counts = (
                update_all_program_service_fetch_counts()
            )
            updated_composite_program_results_count = (
                update_all_composite_program_results_count()
            )
            updated_composite_program_document_counts = (
                update_all_composite_program_document_counts()
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed document counts for {updated_result_count} "
                f"service result(s), result counts for "
                f"{updated_program_service_results_count} program service(s), "
                f"and document, report, and raw data counts for "
                f"{updated_program_service_document_counts} program service(s), "
                f"fetch request, fetched result, fetched document, and pending "
                f"fetch counts for {updated_program_service_fetch_counts} "
                f"program service(s), "
                f"result counts for {updated_composite_program_results_count} "
                f"composite program(s), and document, report, and raw data "
                f"counts for {updated_composite_program_document_counts} "
                f"composite program(s)."
            )
        )
