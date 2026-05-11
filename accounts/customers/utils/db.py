from django.db.models import Case, F, Value, When, Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from accounts.customers.models import CustomerProfile, CustomerCenterAssignment
from accounts.models import UserAccount
from accounts.utils.constants import UserType


def create_customer_user_account(customer):
    """Creates a user account for Customer user type."""
    user = customer.user
    user_account, _ = UserAccount.objects.update_or_create(
        user=user, defaults={"account_type": UserType.CUSTOMER}
    )
    return user_account


def increment_centers_count(customer_profile_id) -> None:
    CustomerProfile.objects.filter(pk=customer_profile_id).update(
        centers_count=F("centers_count") + 1
    )


def decrement_centers_count(customer_profile_id) -> None:
    CustomerProfile.objects.filter(pk=customer_profile_id).update(
        centers_count=Case(
            When(centers_count__gt=0, then=F("centers_count") - 1),
            default=Value(0),
        )
    )


def increment_external_centers_count(customer_profile_id) -> None:
    CustomerProfile.objects.filter(pk=customer_profile_id).update(
        external_centers_count=F("external_centers_count") + 1
    )


def decrement_external_centers_count(customer_profile_id) -> None:
    CustomerProfile.objects.filter(pk=customer_profile_id).update(
        external_centers_count=Case(
            When(external_centers_count__gt=0, then=F("external_centers_count") - 1),
            default=Value(0),
        )
    )


def compute_customer_profile_center_counts(customer_profile_id) -> None:
    """Recompute centers_count and external_centers_count from source of truth."""
    centers_count_subquery = Coalesce(
        Subquery(
            CustomerCenterAssignment.objects.filter(customer_profile_id=OuterRef("pk"))
            .values("customer_profile_id")
            .annotate(count=Count("center_id", distinct=True))
            .values("count")
        ),
        Value(0),
    )

    external_centers_count_subquery = Coalesce(
        Subquery(
            CustomerCenterAssignment.objects.filter(
                customer_profile_id=OuterRef("pk"), is_primary=False
            )
            .values("customer_profile_id")
            .annotate(count=Count("center_id", distinct=True))
            .values("count")
        ),
        Value(0),
    )

    CustomerProfile.objects.filter(pk=customer_profile_id).update(
        centers_count=centers_count_subquery,
        external_centers_count=external_centers_count_subquery,
    )
