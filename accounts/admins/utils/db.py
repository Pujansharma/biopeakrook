from django.db import transaction

from accounts.admins.models import Admin
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType


@transaction.atomic
def create_admin_user(email, password=None, **extra_fields):
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        user = User.objects.create_user(email=email, password=password, **extra_fields)
    account, _ = UserAccount.objects.get_or_create(
        user=user
    )
    account.account_type = UserType.ADMIN
    account.save(update_fields=['account_type'])
    admin, _ = Admin.objects.get_or_create(user=user)
    return admin
