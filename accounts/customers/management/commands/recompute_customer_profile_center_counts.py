from django.core.management.base import BaseCommand

from accounts.customers.utils.db import compute_customer_profile_center_counts
from accounts.customers.models import CustomerProfile


class Command(BaseCommand):
    help = "Recompute centers_count and external_centers_count for all customer profiles from source-of-truth data."

    def handle(self, *args, **options):
        customer_profiles = CustomerProfile.objects.values_list("pk", flat=True)
        updated_count = 0

        for customer_profile_id in customer_profiles:
            compute_customer_profile_center_counts(customer_profile_id)
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Recomputed center counts for {updated_count} customer profile(s)."
            )
        )
