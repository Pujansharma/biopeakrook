from django.core.management.base import BaseCommand
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from programs.services.models import Service, CenterServiceAssignment


class Command(BaseCommand):
    help = "Recompute all denormalized counts on Service from source-of-truth data."

    def handle(self, *args, **options):
        centers_count_subquery = Coalesce(
            Subquery(
                CenterServiceAssignment.objects.filter(
                    service_id=OuterRef("pk"), is_active=True
                )
                .values("service_id")
                .annotate(count=Count("center_id"))
                .values("count")
            ),
            Value(0),
        )

        updated = Service.objects.update(centers_count=centers_count_subquery)

        self.stdout.write(
            self.style.SUCCESS(f"Recomputed counts for {updated} service(s).")
        )
