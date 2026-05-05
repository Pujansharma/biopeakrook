from accounts.utils.permissions import (
    AssociateAdminPermission,
    AssociateFeaturePermission,
)
from core.utils.exceptions import get_object_or_404
from core.utils.views import BaseListCreateAPIView, BaseRetrieveUpdateDestroyAPIView
from inventory.models import Equipment, EquipmentSchedule
from inventory.serializers import EquipmentSerializer, EquipmentScheduleSerializer


class AssociateCenterEquipmentListView(BaseListCreateAPIView):
    """Associate-scoped: list/create equipments for a center."""

    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = EquipmentSerializer

    def get_queryset(self):
        return Equipment.objects.filter(
            center_id=self.request.center_id
        ).select_related("room")

    def perform_create(self, serializer):
        serializer.save(center_id=self.request.center_id, created_by=self.request.user)


class AssociateCenterEquipmentDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Associate-scoped: retrieve/update/delete an equipment."""

    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = EquipmentSerializer

    def get_queryset(self):
        return Equipment.objects.filter(
            center_id=self.request.center_id
        ).select_related("room")


class AssociateCenterEquipmentScheduleListView(BaseListCreateAPIView):
    """Associate-scoped: list/create schedules for equipment."""

    permission_classes = [AssociateAdminPermission | AssociateFeaturePermission]
    serializer_class = EquipmentScheduleSerializer

    def get_equipment(self):
        qs = Equipment.objects.filter(center_id=self.request.center_id)
        return get_object_or_404(
            qs, "Equipment not found for this center", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        return EquipmentSchedule.objects.filter(equipment=self.get_equipment())

    def perform_create(self, serializer):
        serializer.save(equipment=self.get_equipment(), created_by=self.request.user)
