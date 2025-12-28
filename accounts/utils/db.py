from typing import Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import smart_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from accounts.models import UserAccount
from accounts.utils.constants import UserType

User = get_user_model()


def get_user_account(user: User) -> UserAccount:
    account = getattr(user, 'account', None)
    if not account:
        account, _ = UserAccount.objects.get_or_create(user=user)
    return account


def get_user_account_type(user: User):
    if user.is_superuser:
        return UserType.SUPERUSER
    account = get_user_account(user)
    return account.account_type


def get_password_reset_token_for_user(user: User) -> tuple[str, str]:
    uid = urlsafe_base64_encode(str(user.pk).encode('utf-8'))
    token = PasswordResetTokenGenerator().make_token(user)
    return uid, token


def validate_password_reset_token(uid: str, token: str) -> tuple[Optional[User], bool]:
    pk = smart_str(urlsafe_base64_decode(uid))
    user = User.objects.filter(pk=pk).first()
    if not user:
        return None, False
    is_valid = PasswordResetTokenGenerator().check_token(user=user, token=token)
    return user, is_valid
