from django.db.models import Q, ProtectedError, RestrictedError
from rest_framework.permissions import SAFE_METHODS

from accounts.associates.models import AssociateCenterAssignment, AssociateRole
from accounts.associates.serializers import CenterAssociateSerializer, AssociateRoleSerializer
from accounts.customers.models import CustomerCenterAssignment
from accounts.customers.serializers import CenterCustomerProfileSerializer
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
from core.utils.permissions import ReadOnly, ReadUpdateOnly, MODIFY_METHODS
from core.utils.views.main import (
    BaseListCreateAPIView, BaseRetrieveUpdateAPIView,
    BaseRetrieveUpdateDestroyAPIView, BaseGenericAPIView
)
from inventory.models import Room, RoomSchedule, Equipment, EquipmentSchedule
from inventory.serializers import (
    RoomSerializer, RoomScheduleSerializer,
    EquipmentSerializer, EquipmentScheduleSerializer
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
        )

    def get_center(self):
        qs = self.get_center_queryset()
        pk = self.kwargs.get('pk')
        return get_object_or_404(qs, "The selected center could not be found", pk=pk)


class CenterDetailView(BaseRetrieveUpdateDestroyAPIView, CenterViewMeta):
    """Admin-only: center ID from URL path parameter."""
    permission_classes = [IsAdminUser]
    serializer_class = CenterDetailSerializer

    def get_queryset(self):
        return self.get_center_queryset()

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except (ProtectedError, RestrictedError):
            logger.exception(msg="Error in Center DELETE", exc_info=True)
            self.raise_bad_request(
                'This center cannot be deleted since some objects are dependant on it'
            )


class AssociateCenterDetailView(BaseRetrieveUpdateAPIView):
    """
    Associate-scoped: center ID from X-Center-ID header.
    - AssociateAdmins and associates with ALL feature: can retrieve and update.
    """
    permission_classes = [
        (AssociateAdminPermission & ReadUpdateOnly) |
        (AssociateFeaturePermission & ReadUpdateOnly)
    ]
    serializer_class = CenterDetailSerializer

    def get_object(self):
        qs = Center.objects.prefetch_related('created_by')
        return get_object_or_404(
            qs,
            "The selected center could not be found",
            pk=self.request.center_id
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
        qs = Center.objects.only('id', 'name')
        return get_object_or_404(
            qs, "Invalid Center ID provided", pk=center_id
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
    """Associate-scoped: center ID from X-Center-ID header"""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = CenterAssociateSerializer

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get('search', '').strip()

        if search_params:
            search_query |= Q(
                associate__user__first_name__istartswith=search_params
            ) | Q(
                associate__user__first_name__icontains=search_params
            ) | Q(
                associate__user__phone__istartswith=search_params
            ) | Q(
                associate__user__phone__icontains=search_params
            )
        return AssociateCenterAssignment.objects.filter(
            search_query,
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
    - Associates cannot update themselves via this API
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

    def _is_self_associate(self, associate_id):
        return self.request.user.pk == associate_id

    def get_object(self):
        associate_id = self.kwargs.get('pk')

        obj = get_object_or_404(
            queryset=self.get_queryset(),
            detail="Invalid Associate ID",
            associate_id=associate_id,
        )

        if self.request.method in SAFE_METHODS:
            return obj

        if not self._is_non_admin_associate():
            return obj

        # Cannot modify assignments where the current role has ALL feature
        if obj.role and AssociateRoleFeature.ALL in (obj.role.features or []):
            self.raise_permission_denied("You do not have permission to modify this assignment")

        # Cannot modify self details via this
        if self._is_self_associate(obj.associate_id) and self.request.method in MODIFY_METHODS:
            self.raise_permission_denied("You cannot modify your own details")

        return obj

    def perform_update(self, serializer):
        if self._is_non_admin_associate():
            role_id = serializer.validated_data.get('role_id')
            if role_id:
                role = AssociateRole.objects.filter(pk=role_id).first()
                if role and AssociateRoleFeature.ALL in (role.features or []):
                    self.raise_permission_denied("You do not have permission to assign this role")

        serializer.save()

    def perform_destroy(self, instance):
        pass


class AssociateCenterRolesListView(BaseListCreateAPIView):
    """
    Associate-scoped:
     center ID from X-Center-ID header (already validated by RBAC permissions).
    """
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = AssociateRoleSerializer

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get('search', '').strip()
        if search_params:
            search_query |= Q(
                name__istartswith=search_params
            ) | Q(
                name__icontains=search_params
            )

        return AssociateRole.objects.filter(
            search_query, center_id=self.request.center_id
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


class AssociateCenterRoomListView(BaseListCreateAPIView):
    """Associate-scoped: list/create rooms for a center."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = RoomSerializer

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get('search', '').strip()

        if search_params:
            search_query |= Q(
                name__istartswith=search_params
            ) | Q(
                name__icontains=search_params
            ) | Q(
                code__istartswith=search_params
            ) | Q(
                code__icontains=search_params
            )

        return Room.objects.filter(
            search_query, center_id=self.request.center_id
        )

    def perform_create(self, serializer):
        serializer.save(
            center_id=self.request.center_id,
            created_by=self.request.user
        )


class AssociateCenterRoomDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Associate-scoped: retrieve/update/delete a room."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = RoomSerializer

    def get_queryset(self):
        return Room.objects.filter(
            center_id=self.request.center_id
        )


class AssociateCenterRoomScheduleListView(BaseListCreateAPIView):
    """Associate-scoped: list/create schedules for a room."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = RoomScheduleSerializer

    def get_room(self):
        qs = Room.objects.filter(center_id=self.request.center_id)
        return get_object_or_404(
            qs, "Room not found for this center",
            pk=self.kwargs.get('pk')
        )

    def get_queryset(self):
        return RoomSchedule.objects.filter(
            room=self.get_room()
        )

    def perform_create(self, serializer):
        serializer.save(
            room=self.get_room(),
            created_by=self.request.user
        )


class AssociateCenterEquipmentListView(BaseListCreateAPIView):
    """Associate-scoped: list/create equipments for a center."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = EquipmentSerializer

    def get_queryset(self):
        return Equipment.objects.filter(
            center_id=self.request.center_id
        ).select_related('room')

    def perform_create(self, serializer):
        serializer.save(
            center_id=self.request.center_id,
            created_by=self.request.user
        )


class AssociateCenterEquipmentDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Associate-scoped: retrieve/update/delete an equipment."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = EquipmentSerializer

    def get_queryset(self):
        return Equipment.objects.filter(
            center_id=self.request.center_id
        ).select_related('room')


class AssociateCenterEquipmentScheduleListView(BaseListCreateAPIView):
    """Associate-scoped: list/create schedules for equipment."""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = EquipmentScheduleSerializer

    def get_equipment(self):
        qs = Equipment.objects.filter(center_id=self.request.center_id)
        return get_object_or_404(
            qs, "Equipment not found for this center",
            pk=self.kwargs.get('pk')
        )

    def get_queryset(self):
        return EquipmentSchedule.objects.filter(
            equipment=self.get_equipment()
        )

    def perform_create(self, serializer):
        serializer.save(
            equipment=self.get_equipment(),
            created_by=self.request.user
        )


class CenterCustomerProfilesView(BaseListCreateAPIView):
    """Associate Scoped: list/create customers center basis"""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = CenterCustomerProfileSerializer

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get('search', '').strip()

        if search_params:
            search_query |= Q(
                customer_profile__first_name__istartswith=search_params
            ) | Q(
                customer_profile__first_name__icontains=search_params
            ) | Q(
                customer_profile__customer__user__phone__istartswith=search_params
            ) | Q(
                customer_profile__customer__user__phone__icontains=search_params
            )

        return CustomerCenterAssignment.objects.filter(
            search_query,
            center_id=self.request.center_id,
            is_active=True,
        ).select_related(
            'customer_profile__customer__user',
        )

    def perform_create(self, serializer):
        serializer.save(center_id=self.request.center_id)


class CenterCustomerProfileDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Associate Scoped: get/update/delete customers center basis"""
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = CenterCustomerProfileSerializer

    def get_queryset(self):
        return CustomerCenterAssignment.objects.filter(
            center_id=self.request.center_id,
        ).select_related(
            'customer_profile__customer__user',
        )
