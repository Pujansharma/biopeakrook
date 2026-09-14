from rest_framework.permissions import IsAuthenticated

from accounts.associates.utils.constants import AssociateRoleFeature
from accounts.associates.utils.db import get_associate_roles
from accounts.associates.utils.roles import assignment_active_roles
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


class BaseAssociateRBACPermission(IsAssociateUser):
    """Base: validates associate + center assignment."""

    @staticmethod
    def get_center_id(request):
        return request.headers.get("X-Center-ID")

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        associate = getattr(request.user, "associate", None)
        if not associate:
            return False

        center_id = self.get_center_id(request)
        if not center_id:
            return False

        assignment = get_associate_roles(associate, center_id, request)
        if not assignment:
            return False

        request.center_id = center_id
        request.center_assignment = assignment
        return True


class AssociateAdminPermission(BaseAssociateRBACPermission):
    """Requires is_admin=True on center assignment."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        assignment = getattr(request, "center_assignment", None)
        if not assignment:
            return False
        return assignment.is_admin


class AssociateFeaturePermission(BaseAssociateRBACPermission):
    """
    Requires ANY linked role to have ANY of required_any_features (OR).
    Having ALL feature allows.
    """

    required_any_features = []

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        assignment = getattr(request, "center_assignment", None)
        if not assignment:
            return False

        if not self.required_any_features:
            return True

        roles = assignment_active_roles(assignment)
        if not roles:
            return False

        for role in roles:
            if AssociateRoleFeature.ALL in role.features:
                return True
            if any(feature in role.features for feature in self.required_any_features):
                return True
        return False


class AppointmentFeaturePermission(AssociateFeaturePermission):
    required_any_features = [AssociateRoleFeature.APPOINTMENTS]


class AssociateOnboardingPermission(AssociateFeaturePermission):
    required_any_features = [AssociateRoleFeature.ASSOCIATE_ONBOARDING]


class CustomerOnboardingPermission(AssociateFeaturePermission):
    required_any_features = [AssociateRoleFeature.CUSTOMER_ONBOARDING]


class PackagesPermission(AssociateFeaturePermission):
    required_any_features = [AssociateRoleFeature.PACKAGES]
