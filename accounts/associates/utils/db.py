from accounts.associates.models import AssociateCenterAssignment
from accounts.models import UserAccount
from accounts.utils.constants import UserType


def create_associate_user_account(associate):
    """Creates a user account for Associate user type."""
    user = associate.user
    user_account, _ = UserAccount.objects.update_or_create(
        user=user, account_type=UserType.ASSOCIATE
    )
    return user_account


def get_associate_roles(associate, center_id, request=None):
    cache_key = '_center_assignment'

    if request and hasattr(request, cache_key):
        return getattr(request, cache_key)

    assignment = AssociateCenterAssignment.objects.filter(
        associate=associate,
        center_id=center_id,
        is_active=True
    ).select_related('role').first()

    if request:
        setattr(request, cache_key, assignment)

    return assignment
