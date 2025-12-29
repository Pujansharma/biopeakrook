from django.db.models import Q, ProtectedError, RestrictedError

from accounts.centers.models import Center
from accounts.centers.serializers import CenterSerializer, CenterDetailSerializer
from accounts.utils.permissions import IsAdminUser
from core.utils.views.main import BaseListCreateAPIView, BaseRetrieveUpdateDestroyAPIView


class CentersView(BaseListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CenterSerializer

    def get_queryset(self):
        search = Q()
        search_params = self.request.query_params.get('search', '').strip()
        if search_params:
            search |= Q(
                name__istartswith=search_params
            ) | Q(code__icontains=search_params)

        return Center.objects.prefetch_related(
            'created_by'
        ).filter(search)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CenterDetailView(BaseRetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = CenterDetailSerializer

    def get_queryset(self):
        return Center.objects.prefetch_related(
            'created_by'
        ).all()

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except (ProtectedError, RestrictedError) as e:
            return self.send_bad_request(
                'This center cannot be deleted since some objects are dependant on it'
            )
