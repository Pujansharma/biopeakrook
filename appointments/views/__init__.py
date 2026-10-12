from django.db import models

from accounts.centers.models import CenterClosure, CenterOperatingHour
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from appointments.mixins import CenterAvailabilityMixin, AvailabilityExceptionHooksMixin
from appointments.models import (
    AssociateAvailabilityBlock,
    AssociateLeave,
    AssociateRosterEntry,
    CareTeamAvailabilityBlock,
    EquipmentAvailabilityBlock,
    EquipmentDowntime,
    RoomAvailabilityBlock,
    RoomDowntime,
)
from appointments.serializers import (
    AssociateAvailabilityBlockCreateSerializer,
    AssociateAvailabilityBlockSerializer,
    AssociateLeaveSerializer,
    AssociateRosterBulkUpsertSerializer,
    AssociateRosterEntrySerializer,
    CareTeamAvailabilityBlockCreateSerializer,
    CareTeamAvailabilityBlockSerializer,
    CenterClosureSerializer,
    CenterClosureWriteSerializer,
    CenterOperatingHourSerializer,
    CenterOperatingHoursBulkUpsertSerializer,
    EquipmentAvailabilityBlockCreateSerializer,
    EquipmentAvailabilityBlockSerializer,
    EquipmentDowntimeSerializer,
    RoomAvailabilityBlockCreateSerializer,
    RoomAvailabilityBlockSerializer,
    RoomDowntimeSerializer,
)
from appointments.utils.calendar import (
    compute_associate_center_calendar,
    compute_care_team_calendar,
    compute_center_calendar,
    compute_equipment_calendar,
    compute_room_calendar,
    parse_calendar_query_params,
)
from appointments.utils.constants import AvailabilityGranularity, LeaveScope
from appointments.utils.exceptions import (
    pick_exception_scan_status,
    trigger_roster_exception_detection,
)
from core.utils.exceptions import get_object_or_404
from core.utils.log import logger
from core.utils.views.main import (
    BaseGenericAPIView,
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateAPIView,
)
from integrations.google_calendar.availability_sync import (
    sync_google_events_to_availability_blocks,
)
from integrations.google_calendar.connections import (
    connection_is_shared_organizer,
    get_google_calendar_connection_for_user,
    google_calendar_connection_is_connected,
)
from integrations.google_calendar.google_sync import GOOGLE_SYNC_ERRORS
from integrations.google_calendar.webhook_channel import (
    ensure_watch_channel_active_or_log,
)
from inventory.models import Equipment, Room


class CenterAvailabilityCalendarView(CenterAvailabilityMixin, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        center = self.get_center()
        start_date, granularity = parse_calendar_query_params(
            request, default_granularity=AvailabilityGranularity.WEEK
        )
        if granularity not in AvailabilityGranularity.values:
            self.raise_bad_request("Invalid granularity. Use day, week, or month.")
        data = compute_center_calendar(center, start_date, granularity)
        return self.send_response("Center availability retrieved.", data)


class AssociateCenterAvailabilityCalendarView(
    CenterAvailabilityMixin, BaseGenericAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        center = self.get_center()
        associate = self.get_associate()
        start_date, granularity = parse_calendar_query_params(request)
        if granularity not in AvailabilityGranularity.values:
            self.raise_bad_request("Invalid granularity. Use day, week, or month.")
        data = compute_associate_center_calendar(
            center, associate, start_date, granularity
        )
        return self.send_response("Associate availability retrieved.", data)


class CareTeamAvailabilityCalendarView(CenterAvailabilityMixin, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        center = self.get_center()
        care_team = self.get_care_team()
        start_date, granularity = parse_calendar_query_params(request)
        if granularity not in AvailabilityGranularity.values:
            self.raise_bad_request("Invalid granularity. Use day, week, or month.")
        data = compute_care_team_calendar(
            center, care_team, start_date, granularity
        )
        return self.send_response("Care team availability retrieved.", data)


class CareTeamAvailabilityBlockListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    create_success_message = "Care team availability blocks created."

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CareTeamAvailabilityBlockCreateSerializer
        return CareTeamAvailabilityBlockSerializer

    def get_queryset(self):
        center = self.get_center()
        care_team = self.get_care_team()
        filter_kwargs = self.get_active_query_filter()
        return (
            CareTeamAvailabilityBlock.objects.filter(
                center=center, care_team=care_team, **filter_kwargs
            )
            .select_related("care_team", "created_by", "center")
            .order_by("-created_at")
        )

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = serializer.save(
            center=self.get_center(),
            care_team=self.get_care_team(),
            created_by=request.user,
        )
        scan_results = [
            self.apply_exception_side_effects(
                block, serializer.validated_data, created=True
            )
            for block in results
        ]
        data = CareTeamAvailabilityBlockSerializer(results, many=True).data
        response = self.send_response(
            self.create_success_message, data, status=201
        )
        return self.attach_exception_scan(response, scan_results)


class CareTeamAvailabilityBlockDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CareTeamAvailabilityBlockSerializer

    def get_queryset(self):
        center = self.get_center()
        care_team = self.get_care_team()
        return CareTeamAvailabilityBlock.objects.filter(
            center=center, care_team=care_team
        ).select_related("care_team", "created_by", "center")


class RoomAvailabilityCalendarView(CenterAvailabilityMixin, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        center = self.get_center()
        room = get_object_or_404(
            Room.objects.filter(center=center, is_active=True),
            "Room not found.",
            pk=self.kwargs["room_id"],
        )
        start_date, granularity = parse_calendar_query_params(request)
        if granularity not in AvailabilityGranularity.values:
            self.raise_bad_request("Invalid granularity. Use day, week, or month.")
        data = compute_room_calendar(center, room, start_date, granularity)
        return self.send_response("Room availability retrieved.", data)


class EquipmentAvailabilityCalendarView(CenterAvailabilityMixin, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        center = self.get_center()
        equipment = get_object_or_404(
            Equipment.objects.filter(center=center, is_active=True),
            "Equipment not found.",
            pk=self.kwargs["equipment_id"],
        )
        start_date, granularity = parse_calendar_query_params(request)
        if granularity not in AvailabilityGranularity.values:
            self.raise_bad_request("Invalid granularity. Use day, week, or month.")
        data = compute_equipment_calendar(center, equipment, start_date, granularity)
        return self.send_response("Equipment availability retrieved.", data)


class AssociateRosterEntryListView(CenterAvailabilityMixin, BaseListAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateRosterEntrySerializer
    list_success_message = "Associate roster entries retrieved."

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        associate_id = self.request.query_params.get("associate")
        if associate_id is not None:
            filter_kwargs["associate_id"] = associate_id
        return (
            AssociateRosterEntry.objects.filter(center=center, **filter_kwargs)
            .select_related("associate", "created_by", "center")
            .order_by("day_of_week", "-created_at")
        )


class AssociateRosterBulkUpsertView(CenterAvailabilityMixin, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    create_success_message = "Associate roster entries upserted."
    update_success_message = "Associate roster entries updated."

    def post(self, request, *args, **kwargs):
        return self.upsert_roster(request, replace_unlisted=False)

    def patch(self, request, *args, **kwargs):
        return self.upsert_roster(request, replace_unlisted=True)

    def upsert_roster(self, request, replace_unlisted):
        center = self.get_center()
        associate = self.get_associate()
        serializer = AssociateRosterBulkUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = serializer.save(
            center=center,
            associate=associate,
            created_by=request.user,
            replace_unlisted=replace_unlisted,
        )
        scan_result = trigger_roster_exception_detection(center, associate)
        data = AssociateRosterEntrySerializer(results, many=True).data
        message = self.create_success_message
        if request.method != "POST":
            message = self.update_success_message
        response = self.send_response(message, data)
        exception_scan = pick_exception_scan_status([scan_result])
        if exception_scan is not None:
            response.data["exception_scan"] = exception_scan
        return response


class AssociateGoogleCalendarStatusView(CenterAvailabilityMixin, BaseGenericAPIView):
    # For now Admin or associate also, will change as per product decision, lookup of one associate's personal Google Calendar connection.
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get(self, request, *args, **kwargs):
        associate = self.get_associate()
        connection = get_google_calendar_connection_for_user(associate.user)
        return self.send_response(
            "Associate Google Calendar connection status.",
            data={
                "is_connected": google_calendar_connection_is_connected(connection),
                "last_synced_at": connection.last_synced_at if connection else None,
            },
        )


class AssociateGoogleCalendarSyncView(CenterAvailabilityMixin, BaseGenericAPIView):
    # For now Admin or associate also, will change as per product decision
    permission_classes = [IsAdminUser | IsAssociateUser]

    def post(self, request, *args, **kwargs):
        associate = self.get_associate()
        connection = get_google_calendar_connection_for_user(associate.user)
        if not google_calendar_connection_is_connected(connection):
            self.raise_bad_request(
                "This associate hasn't connected a personal Google Calendar."
            )
        if connection_is_shared_organizer(connection):
            self.raise_bad_request(
                "This associate's Google account is the shared appointment "
                "calendar. It cannot also be used for personal calendar sync."
            )

        ensure_watch_channel_active_or_log(connection)

        try:
            summary = sync_google_events_to_availability_blocks(
                associate.user, connection
            )
        except GOOGLE_SYNC_ERRORS as error:
            logger.warning(
                f"Google Calendar availability sync failed for associate "
                f"{associate.pk} (triggered by admin {request.user.pk}): {error}"
            )
            self.raise_bad_request(
                "Failed to sync this associate's Google Calendar. If this "
                "keeps happening, ask them to disconnect and reconnect it."
            )

        return self.send_response("Google Calendar sync completed.", data=summary)


class AssociateAvailabilityBlockListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    create_success_message = "Associate availability blocks created."

    def get_serializer_class(self):
        if self.request.method == "POST":
            return AssociateAvailabilityBlockCreateSerializer
        return AssociateAvailabilityBlockSerializer

    def get_queryset(self):
        center = self.get_center()
        associate = self.get_associate()
        filter_kwargs = self.get_active_query_filter()
        return (
            AssociateAvailabilityBlock.objects.filter(
                center=center, associate=associate, **filter_kwargs
            )
            .select_related("associate", "created_by", "center")
            .order_by("-created_at")
        )

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = serializer.save(
            center=self.get_center(),
            associate=self.get_associate(),
            created_by=request.user,
        )
        scan_results = [
            self.apply_exception_side_effects(
                block, serializer.validated_data, created=True
            )
            for block in results
        ]
        data = AssociateAvailabilityBlockSerializer(results, many=True).data
        response = self.send_response(
            self.create_success_message, data, status=201
        )
        return self.attach_exception_scan(response, scan_results)


class AssociateAvailabilityBlockDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateAvailabilityBlockSerializer

    def get_queryset(self):
        center = self.get_center()
        associate = self.get_associate()
        return AssociateAvailabilityBlock.objects.filter(
            center=center, associate=associate
        ).select_related("associate", "created_by", "center")


class AssociateLeaveListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateLeaveSerializer

    def get_queryset(self):
        center = self.get_center()
        associate = self.get_associate()
        filter_kwargs = self.get_active_query_filter()
        return (
            AssociateLeave.objects.filter(associate=associate, **filter_kwargs)
            .filter(
                models.Q(scope=LeaveScope.ALL_CENTERS)
                | models.Q(center=center)
            )
            .select_related("associate", "created_by", "center")
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["associate"] = self.get_associate()
        context["center"] = self.get_center()
        return context

    def perform_create(self, serializer):
        scope = serializer.validated_data.get("scope", LeaveScope.CENTER)
        center = self.get_center()
        if scope == LeaveScope.ALL_CENTERS:
            center = None
        serializer.save(
            associate=self.get_associate(),
            center=center,
            created_by=self.request.user,
        )
        self.apply_exception_side_effects(
            serializer.instance,
            serializer.validated_data,
            created=True,
        )


class AssociateLeaveDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateLeaveSerializer

    def get_queryset(self):
        center = self.get_center()
        associate = self.get_associate()
        return (
            AssociateLeave.objects.filter(associate=associate)
            .filter(
                models.Q(scope=LeaveScope.ALL_CENTERS)
                | models.Q(center=center)
            )
            .select_related("associate", "created_by", "center")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["associate"] = self.get_associate()
        context["center"] = self.get_center()
        return context


class RoomAvailabilityBlockListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    create_success_message = "Room availability blocks created."

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RoomAvailabilityBlockCreateSerializer
        return RoomAvailabilityBlockSerializer

    def get_room(self):
        return get_object_or_404(
            Room.objects.filter(center=self.get_center(), is_active=True),
            "Room not found.",
            pk=self.kwargs["room_id"],
        )

    def get_queryset(self):
        room = self.get_room()
        filter_kwargs = self.get_active_query_filter()
        return (
            RoomAvailabilityBlock.objects.filter(room=room, **filter_kwargs)
            .select_related("room", "created_by")
            .order_by("-created_at")
        )

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = serializer.save(
            room=self.get_room(),
            created_by=request.user,
        )
        scan_results = [
            self.apply_exception_side_effects(
                block, serializer.validated_data, created=True
            )
            for block in results
        ]
        data = RoomAvailabilityBlockSerializer(results, many=True).data
        response = self.send_response(
            self.create_success_message, data, status=201
        )
        return self.attach_exception_scan(response, scan_results)


class RoomAvailabilityBlockDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomAvailabilityBlockSerializer

    def get_room(self):
        return get_object_or_404(
            Room.objects.filter(center=self.get_center(), is_active=True),
            "Room not found.",
            pk=self.kwargs["room_id"],
        )

    def get_queryset(self):
        room = self.get_room()
        return RoomAvailabilityBlock.objects.filter(room=room).select_related(
            "room", "created_by"
        )


class RoomDowntimeListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomDowntimeSerializer

    def get_room(self):
        return get_object_or_404(
            Room.objects.filter(center=self.get_center(), is_active=True),
            "Room not found.",
            pk=self.kwargs["room_id"],
        )

    def get_queryset(self):
        room = self.get_room()
        filter_kwargs = self.get_active_query_filter()
        return (
            RoomDowntime.objects.filter(room=room, **filter_kwargs)
            .select_related("room", "created_by")
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["room"] = self.get_room()
        return context

    def perform_create(self, serializer):
        serializer.save(room=self.get_room(), created_by=self.request.user)
        self.apply_exception_side_effects(
            serializer.instance,
            serializer.validated_data,
            created=True,
        )


class RoomDowntimeDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RoomDowntimeSerializer

    def get_room(self):
        return get_object_or_404(
            Room.objects.filter(center=self.get_center(), is_active=True),
            "Room not found.",
            pk=self.kwargs["room_id"],
        )

    def get_queryset(self):
        room = self.get_room()
        return RoomDowntime.objects.filter(room=room).select_related(
            "room", "created_by"
        )


class EquipmentAvailabilityBlockListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    create_success_message = "Equipment availability blocks created."

    def get_serializer_class(self):
        if self.request.method == "POST":
            return EquipmentAvailabilityBlockCreateSerializer
        return EquipmentAvailabilityBlockSerializer

    def get_equipment(self):
        return get_object_or_404(
            Equipment.objects.filter(center=self.get_center(), is_active=True),
            "Equipment not found.",
            pk=self.kwargs["equipment_id"],
        )

    def get_queryset(self):
        equipment = self.get_equipment()
        filter_kwargs = self.get_active_query_filter()
        return (
            EquipmentAvailabilityBlock.objects.filter(
                equipment=equipment, **filter_kwargs
            )
            .select_related("equipment", "created_by")
            .order_by("-created_at")
        )

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = serializer.save(
            equipment=self.get_equipment(),
            created_by=request.user,
        )
        scan_results = [
            self.apply_exception_side_effects(
                block, serializer.validated_data, created=True
            )
            for block in results
        ]
        data = EquipmentAvailabilityBlockSerializer(results, many=True).data
        response = self.send_response(
            self.create_success_message, data, status=201
        )
        return self.attach_exception_scan(response, scan_results)


class EquipmentAvailabilityBlockDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentAvailabilityBlockSerializer

    def get_equipment(self):
        return get_object_or_404(
            Equipment.objects.filter(center=self.get_center(), is_active=True),
            "Equipment not found.",
            pk=self.kwargs["equipment_id"],
        )

    def get_queryset(self):
        equipment = self.get_equipment()
        return EquipmentAvailabilityBlock.objects.filter(
            equipment=equipment
        ).select_related("equipment", "created_by")


class EquipmentDowntimeListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentDowntimeSerializer

    def get_equipment(self):
        return get_object_or_404(
            Equipment.objects.filter(center=self.get_center(), is_active=True),
            "Equipment not found.",
            pk=self.kwargs["equipment_id"],
        )

    def get_queryset(self):
        equipment = self.get_equipment()
        filter_kwargs = self.get_active_query_filter()
        return (
            EquipmentDowntime.objects.filter(equipment=equipment, **filter_kwargs)
            .select_related("equipment", "created_by")
            .order_by("-created_at")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["equipment"] = self.get_equipment()
        return context

    def perform_create(self, serializer):
        serializer.save(
            equipment=self.get_equipment(), created_by=self.request.user
        )
        self.apply_exception_side_effects(
            serializer.instance,
            serializer.validated_data,
            created=True,
        )


class EquipmentDowntimeDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EquipmentDowntimeSerializer

    def get_equipment(self):
        return get_object_or_404(
            Equipment.objects.filter(center=self.get_center(), is_active=True),
            "Equipment not found.",
            pk=self.kwargs["equipment_id"],
        )

    def get_queryset(self):
        equipment = self.get_equipment()
        return EquipmentDowntime.objects.filter(equipment=equipment).select_related(
            "equipment", "created_by"
        )

class CenterAvailabilityOperatingHoursView(CenterAvailabilityMixin, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    list_success_message = "Center operating hours retrieved."
    update_success_message = "Center operating hours updated."

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return CenterOperatingHoursBulkUpsertSerializer
        return CenterOperatingHourSerializer

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        return CenterOperatingHour.objects.filter(
            center=center, **filter_kwargs
        ).order_by("day_of_week", "-created_at")

    def get(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = CenterOperatingHourSerializer(queryset, many=True)
        return self.send_response(self.list_success_message, serializer.data)

    def patch(self, request, *args, **kwargs):
        center = self.get_center()
        serializer = CenterOperatingHoursBulkUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        results = serializer.save(center=center)
        data = CenterOperatingHourSerializer(results, many=True).data
        return self.send_response(self.update_success_message, data)


class CenterClosureListCreateView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseListCreateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    list_success_message = "Center closures retrieved."
    create_success_message = "Center closure created."

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CenterClosureWriteSerializer
        return CenterClosureSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["center"] = self.get_center()
        return context

    def get_queryset(self):
        center = self.get_center()
        filter_kwargs = self.get_active_query_filter()
        start_date = self.request.query_params.get("start")
        end_date = self.request.query_params.get("end")
        if start_date:
            filter_kwargs["date__gte"] = start_date
        if end_date:
            filter_kwargs["date__lte"] = end_date
        return CenterClosure.objects.filter(
            center=center, **filter_kwargs
        ).order_by("-date")

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(center=center)
        self.apply_exception_side_effects(
            serializer.instance,
            serializer.validated_data,
            created=True,
        )


class CenterClosureDetailView(
    CenterAvailabilityMixin, AvailabilityExceptionHooksMixin, BaseRetrieveUpdateAPIView
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CenterClosureSerializer
    retrieve_success_message = "Center closure details."
    update_success_message = "Center closure updated."

    def get_queryset(self):
        center = self.get_center()
        return CenterClosure.objects.filter(center=center)