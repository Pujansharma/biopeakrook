from django.core.management.base import BaseCommand

from accounts.admins.models import Admin
from accounts.associates.models import Associate
from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.organizations.models import Organization, OrganizationType


class Command(BaseCommand):
    help = (
        "Recompute all denormalized counts on Organization from source-of-truth data."
    )

    def handle(self, *args, **options):
        org, _ = Organization.objects.get_or_create(
            organization_type=OrganizationType.PLATFORM,
            defaults={"name": "Biopeak Nexus"},
        )

        centers_count = Center.objects.filter(is_active=True).count()
        inactive_centers_count = Center.objects.filter(is_active=False).count()

        staff_count = Associate.objects.count() + Admin.objects.count()
        inactive_staff_count = (
            Associate.objects.filter(user__is_active=False).count()
            + Admin.objects.filter(user__is_active=False).count()
        )

        customer_count = (
            CustomerProfile.objects.filter(
                customer__user__is_active=True,
                is_converted=True,
            )
            .distinct()
            .count()
        )
        inactive_customer_count = (
            CustomerProfile.objects.filter(
                customer__user__is_active=False,
                is_converted=True,
            )
            .distinct()
            .count()
        )

        org.centers_count = centers_count
        org.inactive_centers_count = inactive_centers_count
        org.staff_count = staff_count
        org.inactive_staff_count = inactive_staff_count
        org.customer_count = customer_count
        org.inactive_customer_count = inactive_customer_count
        org.save(
            update_fields=[
                "centers_count",
                "inactive_centers_count",
                "staff_count",
                "inactive_staff_count",
                "customer_count",
                "inactive_customer_count",
            ]
        )

        self.stdout.write(
            self.style.SUCCESS(f"Recomputed counts for organization: {org.id}")
        )
