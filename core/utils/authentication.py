from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.utils import get_user_model
from accounts.utils.db import get_user_account_type
from accounts.verifications.utils.helper import generate_totp_session

User = get_user_model()


def get_tokens_for_user(user: User):
    token = RefreshToken.for_user(user)
    token["email"] = user.email
    token["phone"] = user.phone
    token["user_type"] = get_user_account_type(user)
    return {
        "access": str(token.access_token),
        "refresh": str(token),
    }


def get_mfa_token_for_user(user: User):
    session = generate_totp_session(user)
    return session.token


def perform_login_for_user(user: User):
    data = get_tokens_for_user(user)
    if jwt_settings.UPDATE_LAST_LOGIN:
        update_last_login(User, user)
    return data


class BaseJWTAuthentication(JWTAuthentication):
    pass
