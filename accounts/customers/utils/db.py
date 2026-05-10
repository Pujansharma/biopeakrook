from django.db.models import Case, F, Value, When

from accounts.customers.models import CustomerProfile
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
