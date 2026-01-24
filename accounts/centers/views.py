from django.db.models import Q, ProtectedError, RestrictedError

from accounts.centers.models import Center, CenterOperatingHour
from accounts.centers.serializers import CenterSerializer, CenterDetailSerializer, CenterWorkingHourSerializer
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseListCreateAPIView, BaseRetrieveUpdateDestroyAPIView, BaseGenericAPIView
)


class CentersView(BaseListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CenterSerializer

    def get_queryset(self):
        search = Q()
        search_params = self.request.query_params.get('search', '').strip()
        if search_params:
            search |= Q(
                name__istartswith=search_params
            ) | Q(
                code__icontains=search_params
            )

        return Center.objects.prefetch_related(
            'created_by'
        ).filter(search)

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
    permission_classes = [IsAdminUser]
    serializer_class = CenterDetailSerializer

    def get_queryset(self):
        return self.get_center_queryset()

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except (ProtectedError, RestrictedError) as e:
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
