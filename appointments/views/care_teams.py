from django.db.models import Q

from appointments.mixins import CenterAppointmentsMixin
from appointments.permissions import CenterAppointmentPermission
from appointments.serializers.care_teams import (
    CenterCareTeamSerializer,
    prefetched_care_team_queryset,
)
from core.utils.views.main import BaseListCreateAPIView, BaseRetrieveUpdateAPIView


class CenterCareTeamViewMeta(CenterAppointmentsMixin):
    permission_classes = [CenterAppointmentPermission]
    serializer_class = CenterCareTeamSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_prefetched_queryset(self):
        return prefetched_care_team_queryset().filter(center=self.get_center())


class CenterCareTeamListCreateView(CenterCareTeamViewMeta, BaseListCreateAPIView):
    list_success_message = "Care teams retrieved."
    create_success_message = "Care team created."

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            filter_kwargs["is_active"] = bool(int(active_query))
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        return (
            self.get_prefetched_queryset()
            .filter(search, **filter_kwargs)
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(center=self.get_center(), created_by=self.request.user)


class CenterCareTeamDetailView(CenterCareTeamViewMeta, BaseRetrieveUpdateAPIView):
    retrieve_success_message = "Care team retrieved."
    update_success_message = "Care team updated."

    def get_queryset(self):
        return self.get_prefetched_queryset()
