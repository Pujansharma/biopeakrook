from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import BaseListAPIView
from programs.services.models import Service
from programs.services.serializers import ServiceSerializer


class CenterAssignedServiceView(BaseListAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        qs = Service.objects.filter(centers__id=self.kwargs["pk"])
        return qs
