from django.db.models import Prefetch, Q

from accounts.centers.v2.mixins import CenterV2Mixin
from accounts.centers.v2.serializers import (
    CenterServiceAssignmentV2Serializer,
    CenterServiceV2Serializer,
    EquipmentTypeV2Serializer,
    EquipmentV2Serializer,
    RoomTypeV2Serializer,
    RoomV2Serializer,
)
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateAPIView,
)
from inventory.models import Equipment, EquipmentType, Room, RoomType
from inventory.utils.constants import EquipmentOperationalStatus
from programs.services.models import CenterServiceAssignment, Service


class RoomTypeListCreateView(CenterV2Mixin, BaseListCreateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomTypeV2Serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        return (
            RoomType.objects.filter(search, center=center, **filter_kwargs)
            .select_related("created_by")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(center=center, created_by=self.request.user)


class RoomTypeDetailView(CenterV2Mixin, BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomTypeV2Serializer
    lookup_url_kwarg = "type_id"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        return RoomType.objects.filter(center=center).select_related("created_by")


class EquipmentTypeListCreateView(CenterV2Mixin, BaseListCreateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentTypeV2Serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        return (
            EquipmentType.objects.filter(search, center=center, **filter_kwargs)
            .select_related("created_by")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(center=center, created_by=self.request.user)


class EquipmentTypeDetailView(CenterV2Mixin, BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentTypeV2Serializer
    lookup_url_kwarg = "type_id"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        return EquipmentType.objects.filter(center=center).select_related("created_by")


class RoomListCreateView(CenterV2Mixin, BaseListCreateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomV2Serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        room_type_id = self.request.query_params.get("room_type_id")
        if room_type_id:
            filter_kwargs["room_type_ref"] = room_type_id
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        return (
            Room.objects.filter(search, center=center, **filter_kwargs)
            .select_related("room_type_ref", "created_by")
            .prefetch_related("equipments")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class RoomDetailView(CenterV2Mixin, BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomV2Serializer
    lookup_url_kwarg = "room_id"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        return Room.objects.filter(center=center).select_related(
            "room_type_ref", "created_by"
        ).prefetch_related("equipments")


class EquipmentListCreateView(CenterV2Mixin, BaseListCreateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentV2Serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        equipment_type_id = self.request.query_params.get("equipment_type_id")
        room_id = self.request.query_params.get("room_id")
        operational_status = self.request.query_params.get("operational_status")
        if equipment_type_id:
            filter_kwargs["equipment_type"] = equipment_type_id
        if room_id:
            filter_kwargs["room"] = room_id
        if operational_status in EquipmentOperationalStatus.values:
            filter_kwargs["operational_status"] = operational_status
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
        return (
            Equipment.objects.filter(search, center=center, **filter_kwargs)
            .select_related("equipment_type", "room", "created_by")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class EquipmentDetailView(CenterV2Mixin, BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentV2Serializer
    lookup_url_kwarg = "equipment_id"

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        return Equipment.objects.filter(center=center).select_related(
            "equipment_type", "room", "created_by"
        )


class CenterServiceV2ListView(CenterV2Mixin, BaseListAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CenterServiceV2Serializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def _assignment_prefetch(self, center):
        assignment_filter = {"center": center}
        active_query = self.request.query_params.get("is_active")
        if active_query is None:
            active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            assignment_filter["is_active"] = bool(int(active_query))
        else:
            assignment_filter["is_active"] = True
        return Prefetch(
            "center_assignments",
            queryset=CenterServiceAssignment.objects.filter(**assignment_filter)
            .prefetch_related("role_requirements__role")
            .select_related("required_room_type", "required_equipment_type"),
        )

    def get_queryset(self):
        center = self.get_center()
        assignment_is_active = True
        active_query = self.request.query_params.get("is_active")
        if active_query is None:
            active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            assignment_is_active = bool(int(active_query))

        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        return (
            Service.objects.filter(
                search,
                center_assignments__center=center,
                center_assignments__is_active=assignment_is_active,
            )
            .prefetch_related(self._assignment_prefetch(center))
            .distinct()
            .order_by("-created_at")
        )


class CenterServiceV2DetailView(CenterV2Mixin, BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CenterServiceV2Serializer
    lookup_url_kwarg = "service_id"
    http_method_names = ["get", "patch", "head", "options"]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        return (
            Service.objects.filter(center_assignments__center=center)
            .prefetch_related(
                Prefetch(
                    "center_assignments",
                    queryset=CenterServiceAssignment.objects.filter(center=center)
                    .prefetch_related("role_requirements__role")
                    .select_related("required_room_type", "required_equipment_type"),
                )
            )
            .distinct()
        )

    def get_object(self):
        qs = self.get_queryset()
        return get_object_or_404(
            qs,
            "Service is not assigned to this center.",
            pk=self.kwargs["service_id"],
        )

    def get_assignment(self):
        center = self.get_center()
        service = self.get_object()
        assignment = (
            CenterServiceAssignment.objects.filter(center=center, service=service)
            .prefetch_related("role_requirements__role")
            .select_related("required_room_type", "required_equipment_type")
            .first()
        )
        if not assignment:
            self.raise_bad_request("Service is not assigned to this center.")
        return assignment

    def partial_update(self, request, *args, **kwargs):
        assignment = self.get_assignment()
        serializer = CenterServiceAssignmentV2Serializer(
            assignment,
            data=request.data,
            partial=True,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        service = get_object_or_404(
            self.get_queryset(),
            "Service is not assigned to this center.",
            pk=self.kwargs["service_id"],
        )
        detail = self.get_update_success_message()
        return self.send_response(
            detail,
            CenterServiceV2Serializer(
                service, context=self.get_serializer_context()
            ).data,
        )
