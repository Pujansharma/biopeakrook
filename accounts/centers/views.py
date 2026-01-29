from django.db.models import Q, ProtectedError, RestrictedError
from rest_framework.permissions import SAFE_METHODS

from accounts.associates.models import AssociateCenterAssignment, AssociateRole
from accounts.associates.serializers import CenterAssociateSerializer, AssociateRoleSerializer
from accounts.associates.utils.constants import AssociateRoleFeature
from accounts.centers.models import Center, CenterOperatingHour
from accounts.centers.serializers import (
    CenterSerializer, CenterDetailSerializer, CenterWorkingHourSerializer
)
from accounts.utils.permissions import (
    IsAdminUser, IsAssociateUser, IsCustomerUser, AssociateAdminPermission,
    AssociateFeaturePermission
)
from core.utils.exceptions import get_object_or_404
from core.utils.log import logger
from core.utils.permissions import ReadOnly, ReadUpdateOnly
from core.utils.views.main import (
    BaseListCreateAPIView, BaseRetrieveUpdateDestroyAPIView, BaseGenericAPIView
)


class CentersView(BaseListCreateAPIView):
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]
    serializer_class = CenterSerializer

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_params = self.request.query_params.get('search', '').strip()
        if search_params:
            search |= Q(
                name__istartswith=search_params
            ) | Q(
                code__icontains=search_params
            )
        if associate := getattr(self.request.user, 'associate', None):
            filter_kwargs['associate_assignments__associate'] = associate

        return Center.objects.prefetch_related(
            'created_by'
        ).filter(search, **filter_kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CenterViewMeta(BaseGenericAPIView):
    @classmethod
    def get_center_queryset(cls):
        return Center.objects.prefetch_related(
            'created_by'
        ).all()

    def get_center(self):
        qs = self.get_center_queryset()
        pk = self.kwargs.get('pk')
        return get_object_or_404(qs, pk=pk)


class CenterDetailView(BaseRetrieveUpdateDestroyAPIView, CenterViewMeta):
    permission_classes = [
        IsAdminUser |
        (AssociateAdminPermission & ReadUpdateOnly) |
        (AssociateFeaturePermission & ReadUpdateOnly) |
        (IsAssociateUser & ReadOnly)
    ]
    serializer_class = CenterDetailSerializer

    def get_queryset(self):
        filter_kwargs = {}
        if associate := getattr(self.request, 'associate', None):
            filter_kwargs['associate_assignments__associate'] = associate
        return self.get_center_queryset().filter(**filter_kwargs)

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except (ProtectedError, RestrictedError):
            logger.exception(msg="Error in Center DELETE", exc_info=True)
            self.raise_bad_request(
                'This center cannot be deleted since some objects are dependant on it'
            )


class CenterOperatingHoursView(BaseListCreateAPIView, CenterViewMeta):
    permission_classes = [
        IsAdminUser | (IsAssociateUser & ReadOnly) | (IsCustomerUser & ReadOnly)
    ]
    serializer_class = CenterWorkingHourSerializer

    def get_queryset(self):
        center = self.get_center()
        return CenterOperatingHour.objects.filter(
            center=center
        )

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(center=center)


class CenterHeaderMetaView(BaseGenericAPIView):
    def get_center(self):
        center_id = self.request.headers.get('X-Center-ID')
        if not center_id:
            self.raise_bad_request("X-Center-ID header is required")
        return get_object_or_404(
            Center.objects.only('id', 'name'), "Invalid Center ID provided", pk=center_id
        )


class CenterAssociateListView(BaseListCreateAPIView, CenterViewMeta):
    """Admin-only: center ID from URL path parameter."""
    permission_classes = [IsAdminUser]
    serializer_class = CenterAssociateSerializer

    def get_queryset(self):
        center = self.get_center()
        return AssociateCenterAssignment.objects.filter(
            center_id=center,
            is_active=True
        ).select_related(
            'associate__user',
            'role'
        )


class CenterAssociateRolesListView(BaseListCreateAPIView, CenterViewMeta):
    """Admin-only: center ID from URL path parameter."""
    permission_classes = [IsAdminUser]
    serializer_class = AssociateRoleSerializer

    def get_queryset(self):
        center = self.get_center()
        return AssociateRole.objects.filter(
            center=center
        ).select_related()

    def perform_create(self, serializer):
        serializer.save(
            center=self.get_center(),
            created_by=self.request.user
        )


class AssociateCenterAssociateListView(BaseListCreateAPIView):
    """Associate-scoped: center ID from X-Center-ID header (already validated by RBAC permissions)."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = CenterAssociateSerializer

    def get_queryset(self):
        return AssociateCenterAssignment.objects.filter(
            center_id=self.request.center_id,
            is_active=True
        ).select_related(
            'associate__user',
            'role'
        )

    def perform_create(self, serializer):
        serializer.save(
            center_id=self.request.center_id,
            created_by=self.request.user
        )


class AssociateCenterAssociateDetailView(BaseRetrieveUpdateDestroyAPIView):
    """
    Associate-scoped detail view for updating/deleting a center associate assignment.
    - AssociateAdmins: full access.
    - Associates with ALL feature:
        - Cannot modify assignments where the current role has ALL feature.
        - Cannot assign a role that has ALL feature.
    """
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = CenterAssociateSerializer

    def get_queryset(self):
        return AssociateCenterAssignment.objects.filter(
            center_id=self.request.center_id,
        ).select_related(
            'associate__user',
            'role'
        )

    def _is_non_admin_associate(self):
        return not self.request.center_assignment.is_admin

    def get_object(self):
        obj = super().get_object()

        if self.request.method in SAFE_METHODS:
            return obj

        if not self._is_non_admin_associate():
            return obj

        # Cannot modify assignments where the current role has ALL feature
        if obj.role and AssociateRoleFeature.ALL in (obj.role.features or []):
            self.raise_permission_denied("You do not have permission to modify this assignment")

        return obj

    def perform_update(self, serializer):
        if self._is_non_admin_associate():
            role_id = serializer.validated_data.get('role_id')
            if role_id:
                role = AssociateRole.objects.filter(pk=role_id).first()
                if role and AssociateRoleFeature.ALL in (role.features or []):
                    self.raise_permission_denied("You do not have permission to assign this role")

        serializer.save()


class AssociateCenterRolesListView(BaseListCreateAPIView):
    """Associate-scoped: center ID from X-Center-ID header (already validated by RBAC permissions)."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = AssociateRoleSerializer

    def get_queryset(self):
        search_query = Q()

        return AssociateRole.objects.filter(
            center_id=self.request.center_id
        )

    def perform_create(self, serializer):
        serializer.save(
            center_id=self.request.center_id,
            created_by=self.request.user
        )


class AssociateCenterRoleDetailView(BaseRetrieveUpdateDestroyAPIView):
    """
    Associate-scoped detail view for editing/deleting roles.
    - Admins: full access.
    - AssociateAdmins: can edit any role including ALL-feature roles.
    - Associates with ALL feature: can edit roles that do NOT have ALL feature.
    """
    permission_classes = [IsAdminUser | AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = AssociateRoleSerializer

    def get_queryset(self):
        return AssociateRole.objects.filter(
            center_id=self.request.center_id
        )

    def get_object(self):
        obj = super().get_object()
        assignment = getattr(self.request, 'center_assignment', None)

        # Admins have no center_assignment — allow everything
        if not assignment:
            return obj

        # AssociateAdmins can edit any role
        if assignment.is_admin:
            return obj

        # Non-admin associates cannot edit roles with ALL feature
        if AssociateRoleFeature.ALL in (obj.features or []):
            self.raise_permission_denied("You do not have permission to modify this role")

        return obj
