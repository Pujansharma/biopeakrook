from django.db.models import Q

from accounts.utils.permissions import IsAdminUser
from core.utils.views.main import BaseListCreateAPIView
from programs.services.assessment.serializers import AssessmentServiceSerializer
from programs.services.models import Service
from programs.services.utils.constants import ServiceCategory


class AssessmentServiceListSerializer(BaseListCreateAPIView):
    serializer_class = AssessmentServiceSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_query = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active", None)
        if search_query:
            search |= Q(name__istartswith=search_query)
            search |= Q(name__icontains=search_query)
        if active_query and active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))

        qs = Service.objects.filter(
            search, service_category=ServiceCategory.ASSESSMENT, **filter_kwargs
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            service_category=ServiceCategory.ASSESSMENT
        )
