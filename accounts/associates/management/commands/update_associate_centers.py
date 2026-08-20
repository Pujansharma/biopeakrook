from django.core.management.base import BaseCommand
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from accounts.associates.models import Associate, AssociateCenterAssignment


class Command(BaseCommand):
    help = "Update centers_count for all associates from center assignments."

    def handle(self, *args, **options):
        self.stdout.write("Updating associate center counts...")

        centers_count_subquery = Subquery(
            AssociateCenterAssignment.objects.filter(associate=OuterRef("pk"))
            .order_by()
            .values("associate")
            .annotate(count=Count("center", distinct=True))
            .values("count")
        )
        updated = Associate.objects.update(
            centers_count=Coalesce(centers_count_subquery, Value(0))
        )

        self.stdout.write(
            self.style.SUCCESS(f"Updated center counts for {updated} associate(s).")
        )
