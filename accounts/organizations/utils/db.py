from django.db.models import Count, F, Value, Case, When, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounts.admins.models import Admin
from accounts.associates.models import Associate
from accounts.customers.models import CustomerProfile
from accounts.organizations.models import Organization, OrganizationType
from sequences.utils import get_next_sequence


def get_platform_organization():
    org, _ = Organization.objects.get_or_create(
        organization_type=OrganizationType.PLATFORM, defaults={"name": "Biopeak Nexus"}
    )
    return org


def generate_organization_code() -> str:
    year = timezone.now().year
    sequence = get_next_sequence(name=f"ORG_{year}", fill_length=3)
    return f"ORG-{year}{sequence}"


def increment_organization_centers_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(centers_count=F("centers_count") + 1)


def decrement_organization_centers_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        centers_count=Case(
            When(centers_count__gt=0, then=F("centers_count") - 1),
            default=Value(0),
        )
    )


def increment_organization_inactive_centers_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        inactive_centers_count=F("inactive_centers_count") + 1
    )


def decrement_organization_inactive_centers_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        inactive_centers_count=Case(
            When(inactive_centers_count__gt=0, then=F("inactive_centers_count") - 1),
            default=Value(0),
        )
    )


def increment_organization_admins_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(staff_count=F("staff_count") + 1)


def decrement_organization_admins_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        staff_count=Case(
            When(staff_count__gt=0, then=F("staff_count") - 1),
            default=Value(0),
        )
    )


def increment_organization_inactive_admins_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        inactive_staff_count=F("inactive_staff_count") + 1
    )


def decrement_organization_inactive_admins_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        inactive_staff_count=Case(
            When(inactive_staff_count__gt=0, then=F("inactive_staff_count") - 1),
            default=Value(0),
        )
    )


def increment_organization_clients_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        customer_count=F("customer_count") + 1
    )


def decrement_organization_clients_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        customer_count=Case(
            When(customer_count__gt=0, then=F("customer_count") - 1),
            default=Value(0),
        )
    )


def increment_organization_inactive_clients_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        inactive_customer_count=F("inactive_customer_count") + 1
    )


def decrement_organization_inactive_clients_count() -> None:
    org = get_platform_organization()
    Organization.objects.filter(pk=org.pk).update(
        inactive_customer_count=Case(
            When(inactive_customer_count__gt=0, then=F("inactive_customer_count") - 1),
            default=Value(0),
        )
    )


def update_organization_staff_count() -> None:
    org = get_platform_organization()

    inactive_associate_subquery = Coalesce(
        Subquery(
            Associate.objects.filter(user__is_active=False)
            .values()
            .annotate(count=Count("pk"))
            .values("count")[:1]
        ),
        Value(0),
    )
    inactive_admin_subquery = Coalesce(
        Subquery(
            Admin.objects.filter(user__is_active=False)
            .values()
            .annotate(count=Count("pk"))
            .values("count")[:1]
        ),
        Value(0),
    )

    Organization.objects.filter(pk=org.pk).update(
        inactive_staff_count=inactive_associate_subquery + inactive_admin_subquery,
    )


def update_organization_clients_count() -> None:
    org = get_platform_organization()

    active_count_subquery = Coalesce(
        Subquery(
            CustomerProfile.objects.filter(
                customer__user__is_active=True,
                is_converted=True,
            )
            .values()
            .annotate(count=Count("pk", distinct=True))
            .values("count")[:1]
        ),
        Value(0),
    )
    inactive_count_subquery = Coalesce(
        Subquery(
            CustomerProfile.objects.filter(
                customer__user__is_active=False,
                is_converted=True,
            )
            .values()
            .annotate(count=Count("pk", distinct=True))
            .values("count")[:1]
        ),
        Value(0),
    )

    Organization.objects.filter(pk=org.pk).update(
        customer_count=active_count_subquery,
        inactive_customer_count=inactive_count_subquery,
    )
