from django.db.models import Prefetch

from accounts.customers.models import CustomerCenterAssignment
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
)
from services.programs.models import WellnessProgram
from services.programs.serializers import WellnessProgramSerializer


class CenterProgramsView(BaseListCreateAPIView):
    serializer_class = WellnessProgramSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        center_id = self.kwargs.get("pk")
        filter_kwargs = {}
        active_query_param = self.request.query_params.get('active', None)
        if active_query_param and active_query_param in ['0', '1']:
            filter_kwargs['is_active'] = bool(int(active_query_param))
        qs = (
            WellnessProgram.objects.filter(program__center_id=center_id, **filter_kwargs)
            .select_related(
                "program",
                "program__center",
                "program__created_by",
                "program__customer_profile__customer__user",
            )
            .prefetch_related(
                "program__program_services",
                "program__program_services__service",
                "program__program_services__created_by",
                "program__redeemable_centers",
                Prefetch(
                    "program__customer_profile__center_assignments",
                    queryset=CustomerCenterAssignment.objects.filter(
                        is_primary=True
                    ).select_related("center"),
                    to_attr="primary_center_assignments",
                ),
            )
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(
            center_id=self.kwargs.get("pk"),
            created_by=self.request.user,
        )


class CenterProgramDetails(BaseRetrieveUpdateDestroyAPIView):
    pass
