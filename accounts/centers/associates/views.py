from accounts.associates.models import AssociateCenterAssignment
from accounts.associates.serializers import CenterAssociateDetailSerializer
from accounts.centers.models import Center
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import BaseRetrieveUpdateAPIView


class CenterAssociateDetailView(BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CenterAssociateDetailSerializer

    def get_center(self):
        center_id = self.request.headers.get("x-center-id")
        qs = Center.objects.filter()
        return get_object_or_404(qs, "Invalid center ID provided", pk=center_id)

    def get_queryset(self):
        center = self.get_center()
        return (
            AssociateCenterAssignment.objects.filter(
                center=center,
            )
            .prefetch_related("created_by")
            .select_related("associate__user")
            .prefetch_related("role_links__role")
        )

    def get_object(self):
        qs = self.get_queryset()
        return get_object_or_404(
            qs, "No associate found with the given ID", associate__pk=self.kwargs["pk"]
        )
