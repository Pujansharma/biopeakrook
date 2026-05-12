from typing import Optional

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import smart_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from accounts.models import UserAccount
from accounts.utils import get_user_model
from accounts.utils.constants import UserType

User = get_user_model()


def get_user_account(user: User) -> UserAccount:
    existing: UserAccount | None = getattr(user, "account", None)
    if existing is not None:
        return existing
    account, _ = UserAccount.objects.get_or_create(user=user)
    return account


def get_user_account_type(user: User) -> str:
    if user.is_anonymous:
        return UserType.UNKNOWN
    if user.is_superuser:
        return UserType.SUPERUSER
    account = get_user_account(user)
    return account.account_type


def get_password_reset_token_for_user(user: User) -> tuple[str, str]:
    uid = urlsafe_base64_encode(str(user.pk).encode("utf-8"))
    token = PasswordResetTokenGenerator().make_token(user)
    return uid, token


def validate_password_reset_token(uid: str, token: str) -> tuple[Optional[User], bool]:
    pk = smart_str(urlsafe_base64_decode(uid))
    user = User.objects.filter(pk=pk).first()
    if not user:
        return None, False
    is_valid = PasswordResetTokenGenerator().check_token(user=user, token=token)
    return user, is_valid


def check_user_exists(email: str = None, phone: str = None) -> dict[str, str]:
    """Check if the user exists by email and/or phone.

    For admins/associates: only email is checked (phone must be None).
    For customers: only phone is checked (email must be None).
    """
    errors = {}
    if email and User.objects.filter(email__iexact=email).exists():
        errors["email"] = "User with this email already exists."
    if phone and User.objects.filter(phone__iexact=phone).exists():
        errors["phone"] = "User with this phone already exists."
    return errors


def check_admin_associate_user_exists(email: str) -> dict[str, str]:
    """Check if admin/associate user exists by email only."""
    errors = {}
    if email and User.objects.filter(email__iexact=email).exists():
        errors["email"] = "User with this email already exists."
    return errors


def check_customer_user_exists(phone: str) -> dict[str, str]:
    """Check if customer user exists by phone only."""
    errors = {}
    if phone and User.objects.filter(phone__iexact=phone).exists():
        errors["phone"] = "User with this phone already exists."
    return errors
