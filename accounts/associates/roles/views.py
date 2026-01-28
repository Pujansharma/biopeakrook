from accounts.associates.serializers import AssociateRoleSerializer
from accounts.centers.views import CenterHeaderMetaView
from accounts.utils.permissions import AssociateFeaturePermission, AssociateAdminPermission
from core.utils.views.main import BaseListCreateAPIView


class AssociateRolesView(BaseListCreateAPIView,CenterHeaderMetaView):
    """View for center admins & associates with roles to create roles"""
    serializer_class = AssociateRoleSerializer
    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]

    def get_queryset(self):
        center = self.get_center()