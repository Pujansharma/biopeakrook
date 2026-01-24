from rest_framework.permissions import IsAuthenticated

from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type


class IsAdminUser(IsAuthenticated):
    def has_permission(self, request, view):
        user_account = get_user_account_type(user=request.user)
        return user_account == UserType.ADMIN


class IsAssociateUser(IsAuthenticated):
    def has_permission(self, request, view):
        user_account = get_user_account_type(user=request.user)
        return user_account == UserType.ASSOCIATE


class IsCustomerUser(IsAuthenticated):
    def has_permission(self, request, view):
        user_account = get_user_account_type(user=request.user)
        return user_account == UserType.CUSTOMER
