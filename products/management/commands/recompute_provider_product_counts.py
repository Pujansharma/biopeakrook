from django.core.management.base import BaseCommand

from products.utils.db import update_all_provider_products_count


class Command(BaseCommand):
    help = "Recompute products_count on Provider from source-of-truth data."

    def handle(self, *args, **options):
        updated_count = update_all_provider_products_count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed product counts for {updated_count} provider(s)."
            )
        )
