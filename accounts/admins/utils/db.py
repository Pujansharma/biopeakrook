from django.db import transaction

from accounts.admins.models import Admin
from accounts.models import UserAccount
from accounts.users.models import User
from accounts.utils.constants import UserType


@transaction.atomic
def create_admin_user(email, password=None, **extra_fields):
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        user = User.objects.create_user(
            email=email, password=password, phone=None, **extra_fields
        )
    account, _ = UserAccount.objects.get_or_create(user=user)
    account.account_type = UserType.ADMIN
    account.save(update_fields=["account_type"])
    admin, _ = Admin.objects.update_or_create(
        user=user, defaults={"created_by": extra_fields.get("created_by")}
    )
    return admin
