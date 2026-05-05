from django.db.models import F, Value, Case, When
from django.utils import timezone

from accounts.organizations.models import Organization
from sequences.utils import get_next_sequence


def generate_organization_code() -> str:
    year = timezone.now().year
    sequence = get_next_sequence(name=f"ORG_{year}", fill_length=3)
    return f"ORG-{year}{sequence}"


def increment_centers_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(centers_count=F("centers_count") + 1)


def decrement_centers_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        centers_count=Case(
            When(centers_count__gt=0, then=F("centers_count") - 1),
            default=Value(0),
        )
    )


def increment_inactive_centers_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        inactive_centers_count=F("inactive_centers_count") + 1
    )


def decrement_inactive_centers_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        inactive_centers_count=Case(
            When(inactive_centers_count__gt=0, then=F("inactive_centers_count") - 1),
            default=Value(0),
        )
    )


def increment_staff_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(staff_count=F("staff_count") + 1)


def decrement_staff_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        staff_count=Case(
            When(staff_count__gt=0, then=F("staff_count") - 1),
            default=Value(0),
        )
    )


def increment_inactive_staff_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        inactive_staff_count=F("inactive_staff_count") + 1
    )


def decrement_inactive_staff_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        inactive_staff_count=Case(
            When(inactive_staff_count__gt=0, then=F("inactive_staff_count") - 1),
            default=Value(0),
        )
    )


def increment_customer_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        customer_count=F("customer_count") + 1
    )


def decrement_customer_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        customer_count=Case(
            When(customer_count__gt=0, then=F("customer_count") - 1),
            default=Value(0),
        )
    )


def increment_inactive_customer_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        inactive_customer_count=F("inactive_customer_count") + 1
    )


def decrement_inactive_customer_count(org_id) -> None:
    Organization.objects.filter(pk=org_id).update(
        inactive_customer_count=Case(
            When(inactive_customer_count__gt=0, then=F("inactive_customer_count") - 1),
            default=Value(0),
        )
    )
