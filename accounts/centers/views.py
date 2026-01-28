from django.db.models import Q, ProtectedError, RestrictedError

from accounts.associates.models import AssociateCenterAssignment, AssociateRole
from accounts.associates.serializers import CenterAssociateListSerializer, AssociateRoleSerializer
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
            return self.send_bad_request(
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
        qs = Center.objects.select_related()
        return get_object_or_404(
            qs, "Invalid Center ID provided", pk=center_id
        )


class CenterAssociateListView(BaseListCreateAPIView, CenterViewMeta):
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = CenterAssociateListSerializer

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
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = AssociateRoleSerializer

    def get_queryset(self):
        center = self.get_center()
        return AssociateRole.objects.filter(
            center=center
        ).select_related()
