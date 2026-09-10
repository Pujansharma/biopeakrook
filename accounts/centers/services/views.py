from django.db.models import Prefetch

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import BaseListAPIView
from programs.services.models import CenterServiceAssignment, Service
from programs.services.serializers import ServiceSerializer


class CenterAssignedServiceView(BaseListAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        center_id = self.kwargs["pk"]
        return (
            Service.objects.filter(center_assignments__center_id=center_id)
            .prefetch_related(
                Prefetch(
                    "center_assignments",
                    queryset=CenterServiceAssignment.objects.filter(
                        center_id=center_id
                    ).select_related("center"),
                )
            )
            .select_related("created_by")
            .order_by("-created_at")
            .distinct()
        )
