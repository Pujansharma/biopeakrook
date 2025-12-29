from django.db.models import Q

from accounts.centers.models import Center
from accounts.centers.serializers import CenterSerializer
from accounts.utils.permissions import IsAdminUser
from core.utils.views.main import BaseListCreateAPIView


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

        return Center.objects.filter(search)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
