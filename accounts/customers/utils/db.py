from accounts.models import UserAccount
from accounts.utils.constants import UserType


def create_customer_user_account(customer):
    """Creates a user account for Customer user type."""
    user = customer.user
    user_account, _ = UserAccount.objects.update_or_create(
        user=user, defaults={'account_type': UserType.CUSTOMER}
    )
    return user_account
