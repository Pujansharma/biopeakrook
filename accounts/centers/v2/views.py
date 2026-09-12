import re

from django.db.models import Exists, OuterRef, Prefetch, Q

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
from core.utils.constants import AppointmentModes
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateAPIView,
)
from inventory.models import Equipment, EquipmentType, Room, RoomType
from inventory.utils.constants import EquipmentOperationalStatus
from programs.services.models import (
    CenterServiceAssignment,
    CenterServiceRoleRequirement,
    CenterServiceRoomTypeRequirement,
    Service,
)

UUID_QUERY_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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
        room_type_id = (self.request.query_params.get("room_type_id") or "").strip()
        if room_type_id:
            if UUID_QUERY_PATTERN.fullmatch(room_type_id) is None:
                self.raise_bad_request("Invalid room_type_id.")
            filter_kwargs["room_type_ref"] = room_type_id
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        type_active_query = self.request.query_params.get("type_active")
        type_active_filters = {
            "1": Q(room_type_ref__isnull=False, room_type_ref__is_active=True),
            "0": Q(room_type_ref__isnull=True) | Q(room_type_ref__is_active=False),
        }
        type_active_filter = type_active_filters.get(type_active_query, Q())

        return (
            Room.objects.filter(
                search,
                type_active_filter,
                center=center,
                **filter_kwargs,
            )
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

        type_active_query = self.request.query_params.get("type_active")
        type_active_filters = {
            "1": Q(equipment_type__isnull=False, equipment_type__is_active=True),
            "0": Q(equipment_type__isnull=True) | Q(equipment_type__is_active=False),
        }
        type_active_filter = type_active_filters.get(type_active_query, Q())

        room_allotted_query = self.request.query_params.get("room_allotted")
        room_allotted_filters = {
            "1": Q(room__isnull=False, room__is_active=True),
            "0": Q(room__isnull=True) | Q(room__is_active=False),
        }
        room_allotted_filter = room_allotted_filters.get(room_allotted_query, Q())

        return (
            Equipment.objects.filter(
                search,
                type_active_filter,
                room_allotted_filter,
                center=center,
                **filter_kwargs,
            )
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
        active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            assignment_filter["is_active"] = bool(int(active_query))
        return Prefetch(
            "center_assignments",
            queryset=CenterServiceAssignment.objects.filter(**assignment_filter)
            .prefetch_related(
                "role_requirements__role",
                "room_type_requirements__room_type",
            ),
        )

    def get_queryset(self):
        center = self.get_center()
        assignment_filter = {"center_assignments__center": center}
        active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            assignment_filter["center_assignments__is_active"] = bool(
                int(active_query)
            )

        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        min_duration_met_query = self.request.query_params.get("min_duration_met")
        min_duration_met_filters = {
            "1": Exists(
                CenterServiceAssignment.objects.filter(
                    service_id=OuterRef("pk"),
                    center=center,
                    duration__gte=30,
                )
            ),
            "0": Exists(
                CenterServiceAssignment.objects.filter(
                    Q(duration__isnull=True) | Q(duration__lt=30),
                    service_id=OuterRef("pk"),
                    center=center,
                )
            ),
        }
        min_duration_met_filter = min_duration_met_filters.get(
            min_duration_met_query, Q()
        )

        has_active_role = Exists(
            CenterServiceRoleRequirement.objects.filter(
                assignment__service_id=OuterRef("pk"),
                assignment__center=center,
                is_active=True,
                role__is_active=True,
            )
        )
        has_live_room = Exists(
            CenterServiceRoomTypeRequirement.objects.filter(
                assignment__service_id=OuterRef("pk"),
                assignment__center=center,
                is_active=True,
                room_type__is_active=True,
            )
        )
        is_virtual_assignment = Exists(
            CenterServiceAssignment.objects.filter(
                service_id=OuterRef("pk"),
                center=center,
                modality=AppointmentModes.VIRTUAL,
            )
        )
        resource_ready = Q(is_virtual_assignment=True, has_active_role=True) | (
            Q(is_virtual_assignment=False)
            & Q(has_active_role=True)
            & Q(has_live_room=True)
        )
        resource_active_filters = {
            "1": resource_ready,
            "0": ~resource_ready,
        }
        resource_active_query = self.request.query_params.get("resource_active")
        resource_active_filter = resource_active_filters.get(
            resource_active_query, Q()
        )

        return (
            Service.objects.annotate(
                has_active_role=has_active_role,
                has_live_room=has_live_room,
                is_virtual_assignment=is_virtual_assignment,
            )
            .filter(
                search,
                min_duration_met_filter,
                resource_active_filter,
                **assignment_filter,
            )
            .prefetch_related(self._assignment_prefetch(center))
            .distinct()
            .order_by("-created_at")
        )


class CenterServiceV2DetailView(CenterV2Mixin, BaseRetrieveUpdateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CenterServiceV2Serializer
    lookup_url_kwarg = "service_id"

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
                    .prefetch_related(
                        "role_requirements__role",
                        "room_type_requirements__room_type",
                    ),
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
            .prefetch_related(
                "role_requirements__role",
                "room_type_requirements__room_type",
            )
            .first()
        )
        if not assignment:
            self.raise_bad_request("Service is not assigned to this center.")
        return assignment

    def partial_update(self, request, *args, **kwargs):
        if not isinstance(request.data, dict):
            self.raise_bad_request(
                "Invalid Request"
                'Check the request body and try again.'
            )
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
