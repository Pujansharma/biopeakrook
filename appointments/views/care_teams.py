from django.db.models import Exists, OuterRef, Prefetch, Q

from accounts.associates.models import AssociateCenterAssignmentRole
from appointments.mixins import CenterAppointmentsMixin
from appointments.models import CenterCareTeam, CenterCareTeamMember
from appointments.permissions import CenterAppointmentPermission
from appointments.serializers.care_teams import CenterCareTeamSerializer
from core.utils.views.main import BaseListCreateAPIView, BaseRetrieveUpdateAPIView


class CenterCareTeamViewMeta(CenterAppointmentsMixin):
    permission_classes = [CenterAppointmentPermission]
    serializer_class = CenterCareTeamSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        filter_kwargs = {}
        return CenterCareTeam.objects.filter(
            center=self.get_center(), **filter_kwargs
        ).prefetch_related(
            Prefetch(
                "members",
                queryset=CenterCareTeamMember.objects.select_related(
                    "associate__user",
                    "role",
                ).order_by("role"),
                to_attr="prefetched_members",
            )
        )

    def reload_prefetched_instance(self, instance):
        return CenterCareTeamViewMeta.get_queryset(self).filter(pk=instance.pk).first()


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
        has_broken_member = Exists(
            CenterCareTeamMember.objects.filter(
                care_team_id=OuterRef("pk"),
            ).exclude(
                Exists(
                    AssociateCenterAssignmentRole.objects.filter(
                        assignment__associate_id=OuterRef("associate_id"),
                        assignment__center_id=OuterRef("care_team__center_id"),
                        assignment__is_active=True,
                        assignment__associate__user__is_active=True,
                        is_active=True,
                        role_id=OuterRef("role_id"),
                        role__is_active=True,
                    )
                )
            )
        )
        members_live_filters = {
            "1": ~has_broken_member,
            "0": has_broken_member,
        }
        members_live_filter = members_live_filters.get(
            self.request.query_params.get("members_live"),
            Q(),
        )
        return (
            super()
            .get_queryset()
            .filter(
                search,
                members_live_filter,
                **filter_kwargs,
            )
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(center=self.get_center(), created_by=self.request.user)
        serializer.instance = self.reload_prefetched_instance(serializer.instance)


class CenterCareTeamDetailView(CenterCareTeamViewMeta, BaseRetrieveUpdateAPIView):
    retrieve_success_message = "Care team retrieved."
    update_success_message = "Care team updated."

    def perform_update(self, serializer):
        super().perform_update(serializer)
        serializer.instance = self.reload_prefetched_instance(serializer.instance)
