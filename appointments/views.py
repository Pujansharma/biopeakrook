from accounts.utils.permissions import IsAssociateUser
from appointments.serializers import ScheduleSerializer
from core.utils.views.main import BaseListCreateAPIView


class AssociateScheduleView(BaseListCreateAPIView):
    permission_classes = [IsAssociateUser]
    serializer_class = ScheduleSerializer

    def get_queryset(self):
        pass

    def perform_create(self, serializer):
        specialist = None
        serializer.save(specialist=specialist)
