from accounts.associates.models import AssociateCenterAssignment
from accounts.customers.models import CustomerCenterAssignment
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from rest_framework.permissions import BasePermission


def customer_has_center_access(user, center_id):
    if not hasattr(user, "customer"):
        return False
    return CustomerCenterAssignment.objects.filter(
        customer_profile__customer=user.customer,
        center_id=center_id,
        is_active=True,
    ).exists()


class CenterAppointmentPermission(BasePermission):
    """Staff access to center-scoped appointment APIs (URL center_id authoritative)."""

    def has_permission(self, request, view):
        if not (
            IsAdminUser().has_permission(request, view)
            or IsAssociateUser().has_permission(request, view)
        ):
            return False
        center_id = view.kwargs.get("center_id")
        if center_id is None:
            return False
        account_type = get_user_account_type(request.user)
        if account_type == UserType.ADMIN:
            return self._admin_center_allowed(request, center_id)
        if account_type == UserType.ASSOCIATE:
            return self._associate_center_allowed(request, center_id)
        return False

    def _admin_center_allowed(self, request, center_id):
        if not hasattr(request.user, "associate"):
            return True
        active_assignments = AssociateCenterAssignment.objects.filter(
            associate=request.user.associate,
            is_active=True,
        )
        if not active_assignments.exists():
            return True
        return active_assignments.filter(center=center_id).exists()

    def _associate_center_allowed(self, request, center_id):
        if not hasattr(request.user, "associate"):
            return False
        return AssociateCenterAssignment.objects.filter(
            associate=request.user.associate,
            is_active=True,
            center=center_id,
        ).exists()


class CustomerCenterAppointmentPermission(BasePermission):
    """Customer access when they have an active profile assignment at URL center."""

    def has_permission(self, request, view):
        if not IsCustomerUser().has_permission(request, view):
            return False
        center_id = view.kwargs.get("center_id")
        if center_id is None:
            return False
        return customer_has_center_access(request.user, center_id)


class StaffOrCustomerCenterAppointmentPermission(BasePermission):
    """Staff (admin/associate) or customer with center assignment."""

    def has_permission(self, request, view):
        if CenterAppointmentPermission().has_permission(request, view):
            return True
        return CustomerCenterAppointmentPermission().has_permission(request, view)
