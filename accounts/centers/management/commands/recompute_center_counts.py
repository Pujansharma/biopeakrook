from django.core.management.base import BaseCommand
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from accounts.associates.models import AssociateCenterAssignment
from accounts.centers.models import Center
from accounts.customers.models import CustomerCenterAssignment


class Command(BaseCommand):
    help = "Recompute all denormalized counts on Center from source-of-truth data."

    def handle(self, *args, **options):
        staff_subquery = Coalesce(
            Subquery(
                AssociateCenterAssignment.objects.filter(
                    center=OuterRef("pk"),
                )
                .values("center")
                .annotate(c=Count("pk"))
                .values("c")
            ),
            Value(0),
        )

        inactive_staff_subquery = Coalesce(
            Subquery(
                AssociateCenterAssignment.objects.filter(
                    center=OuterRef("pk"),
                    associate__user__is_active=False,
                )
                .values("center")
                .annotate(c=Count("pk"))
                .values("c")
            ),
            Value(0),
        )

        customer_subquery = Coalesce(
            Subquery(
                CustomerCenterAssignment.objects.filter(
                    center=OuterRef("pk"),
                    customer_profile__is_converted=True,
                )
                .values("center")
                .annotate(c=Count("pk"))
                .values("c")
            ),
            Value(0),
        )

        inactive_customer_subquery = Coalesce(
            Subquery(
                CustomerCenterAssignment.objects.filter(
                    center=OuterRef("pk"),
                    customer_profile__customer__user__is_active=False,
                    customer_profile__is_converted=True,
                )
                .values("center")
                .annotate(c=Count("pk"))
                .values("c")
            ),
            Value(0),
        )

        updated = Center.objects.update(
            staff_count=staff_subquery,
            inactive_staff_count=inactive_staff_subquery,
            customer_count=customer_subquery,
            inactive_customer_count=inactive_customer_subquery,
        )

        self.stdout.write(
            self.style.SUCCESS(f"Recomputed counts for {updated} center(s).")
        )
