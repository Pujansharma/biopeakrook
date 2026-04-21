from django.core.management.base import BaseCommand
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from accounts.centers.models import Center
from accounts.organizations.models import Organization


class Command(BaseCommand):
    help = 'Recompute all denormalized counts on Organization from source-of-truth data.'

    def handle(self, *args, **options):
        # Requires Center.organization FK to be present
        centers_subquery = Coalesce(Subquery(
            Center.objects.filter(
                organization=OuterRef('pk'),
            ).values('organization').annotate(c=Count('pk')).values('c')
        ), Value(0))

        inactive_centers_subquery = Coalesce(Subquery(
            Center.objects.filter(
                organization=OuterRef('pk'),
                is_active=False,
            ).values('organization').annotate(c=Count('pk')).values('c')
        ), Value(0))

        staff_subquery = Coalesce(Subquery(
            Center.objects.filter(
                organization=OuterRef('pk'),
            ).values('organization').annotate(
                c=Count('associate_assignments__associate', distinct=True)
            ).values('c')
        ), Value(0))

        inactive_staff_subquery = Coalesce(Subquery(
            Center.objects.filter(
                organization=OuterRef('pk'),
            ).values('organization').annotate(
                c=Count(
                    'associate_assignments__associate',
                    filter=Count('associate_assignments__associate__user__is_active'),
                    distinct=True,
                )
            ).values('c')
        ), Value(0))

        customer_subquery = Coalesce(Subquery(
            Center.objects.filter(
                organization=OuterRef('pk'),
            ).values('organization').annotate(
                c=Count('customer_assignments__customer_profile', distinct=True)
            ).values('c')
        ), Value(0))

        inactive_customer_subquery = Coalesce(Subquery(
            Center.objects.filter(
                organization=OuterRef('pk'),
            ).values('organization').annotate(
                c=Count(
                    'customer_assignments__customer_profile',
                    distinct=True,
                )
            ).values('c')
        ), Value(0))

        updated = Organization.objects.update(
            centers_count=centers_subquery,
            inactive_centers_count=inactive_centers_subquery,
            staff_count=staff_subquery,
            inactive_staff_count=inactive_staff_subquery,
            customer_count=customer_subquery,
            inactive_customer_count=inactive_customer_subquery,
        )

        self.stdout.write(self.style.SUCCESS(f'Recomputed counts for {updated} organization(s).'))
