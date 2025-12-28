from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.utils.db import get_user_account_type


def get_tokens_for_user(user):
    token = RefreshToken.for_user(user)
    token['email'] = user.email
    token['phone'] = user.phone
    token['user_type'] = get_user_account_type(user)
    return {
        'access': str(token.access_token),
        'refresh': str(token),
    }


def perform_login_for_user(user):
    data = get_tokens_for_user(user)
    if jwt_settings.UPDATE_LAST_LOGIN:
        update_last_login(None, user)
    return data


class BaseJWTAuthentication(JWTAuthentication):
    pass
