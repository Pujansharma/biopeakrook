import hashlib
import json
import time
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from appointments.mixins import CenterAppointmentsMixin
from appointments.models import (
    Appointment,
    AppointmentAssociate,
    AppointmentAuditLog,
    AppointmentHistory,
    AppointmentIdempotencyKey,
)
from appointments.permissions import CenterAppointmentPermission
from appointments.serializers.booking import (
    AppointmentBookSerializer,
    AppointmentCancelSerializer,
    AppointmentDetailSerializer,
    AppointmentLifecycleSerializer,
    AppointmentListSerializer,
    AppointmentMarkLateSerializer,
    AppointmentRescheduleSerializer,
    AppointmentSlotFindSerializer,
)
from appointments.utils.care_teams import (
    care_team_associates_payload,
    expand_care_team_for_assignment,
)
from appointments.utils.calendar import get_center_timezone_name, parse_calendar_query_params
from appointments.utils.codes import generate_appointment_code
from appointments.utils.constants import (
    AppointmentAuditAction,
    AppointmentStatus,
    AvailabilityGranularity,
    ExceptionResolution,
)
from appointments.utils.exceptions import (
    detect_exceptions_for_appointment,
    resolve_exceptions_for_appointment,
)
from appointments.utils.operations import invalidate_operations_cache
from appointments.utils.intervals import datetime_range_for_dates, resolve_query_date_range
from appointments.utils.metrics import (
    log_appointment_event,
    record_book_outcome,
    record_lifecycle,
    record_slots_duration,
)
from appointments.utils.scheduling import (
    compute_exclusive_bounds,
    find_appointment_slots,
    get_center_service_assignment,
    validate_appointment_allocation,
)
from appointments.utils.transitions import apply_status_change, sync_associate_status_snapshots
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import BaseGenericAPIView, BaseListAPIView, BaseRetrieveAPIView
from inventory.models import Equipment, Room

LIST_CAP = 500
IDEMPOTENCY_TTL_HOURS = 24

ACTION_AUDIT_MAP = {
    "check-in": AppointmentAuditAction.CHECK_IN,
    "start": AppointmentAuditAction.START,
    "mark-late": AppointmentAuditAction.MARK_LATE,
    "complete": AppointmentAuditAction.COMPLETE,
    "no-show": AppointmentAuditAction.NO_SHOW,
    "cancel": AppointmentAuditAction.CANCEL,
    "reschedule": AppointmentAuditAction.RESCHEDULE,
}


class ConflictError(APIException):
    status_code = 409
    default_detail = "Conflict."
    default_code = "conflict"


class AppointmentBookingMixin(CenterAppointmentsMixin):
    permission_classes = [CenterAppointmentPermission]


def canonical_payload_hash(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def resolve_room(center, room_id):
    if room_id is None:
        return None
    return get_object_or_404(
        Room.objects.filter(center=center, is_active=True),
        "Room not found.",
        pk=room_id,
    )


def resolve_equipment(center, equipment_id):
    if equipment_id is None:
        return None
    return get_object_or_404(
        Equipment.objects.filter(center=center, is_active=True),
        "Equipment not found.",
        pk=equipment_id,
    )


def create_audit_log(appointment, actor, action, note=""):
    AppointmentAuditLog.objects.create(
        appointment=appointment,
        actor=actor,
        action=action,
        note=note,
    )


def build_associate_payload(raw_associates):
    payload = []
    for entry in raw_associates:
        payload.append(
            {
                "role_id": str(entry["role_id"]),
                "associate_id": entry["associate_id"],
            }
        )
    return payload


def create_appointment_associates(appointment, associates_payload, exclusive_start, exclusive_end):
    for entry in associates_payload:
        AppointmentAssociate.objects.create(
            appointment=appointment,
            associate_id=entry["associate_id"],
            role_id=entry["role_id"],
            exclusive_start_datetime=exclusive_start,
            exclusive_end_datetime=exclusive_end,
            appointment_status=appointment.status,
        )


def resolve_booking_associates(center, assignment, validated):
    care_team_id = validated.get("care_team_id")
    if care_team_id:
        members = expand_care_team_for_assignment(
            center, care_team_id, assignment
        )
        return care_team_associates_payload(members), members[0].care_team
    return build_associate_payload(validated["associates"]), None


def create_appointment_record(
    center,
    validated_data,
    assignment,
    room,
    equipment,
    actor,
    associates_payload,
    care_team,
):
    start = validated_data["start"]
    end = validated_data["end"]
    buffer_before = assignment.buffer_before
    buffer_after = assignment.buffer_after
    exclusive_start, exclusive_end = compute_exclusive_bounds(
        start, end, buffer_before, buffer_after
    )
    appointment = Appointment.objects.create(
        center=center,
        code=generate_appointment_code(center),
        customer_profile=validated_data["customer_profile"],
        service=validated_data["service"],
        modality=validated_data["modality"],
        start_datetime=start,
        end_datetime=end,
        duration_minutes=assignment.duration,
        buffer_before_minutes=buffer_before,
        buffer_after_minutes=buffer_after,
        exclusive_start_datetime=exclusive_start,
        exclusive_end_datetime=exclusive_end,
        status=AppointmentStatus.CONFIRMED,
        room=room,
        equipment=equipment,
        care_team=care_team,
        created_by=actor,
    )
    create_appointment_associates(
        appointment,
        associates_payload,
        exclusive_start,
        exclusive_end,
    )
    create_audit_log(appointment, actor, AppointmentAuditAction.CREATE)
    return appointment


def dispatch_to_view(view_class, request, *args, **kwargs):
    """Run a sibling view handler without wrapping the DRF request twice."""
    view = view_class()
    view.request = request
    view.args = args
    view.kwargs = kwargs
    view.format_kwarg = None
    handler = getattr(view, request.method.lower())
    return handler(request, *args, **kwargs)


class AppointmentCollectionView(AppointmentBookingMixin, BaseGenericAPIView):
    """GET list + POST book at /appointments/."""

    def get(self, request, *args, **kwargs):
        return dispatch_to_view(AppointmentListView, request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return dispatch_to_view(AppointmentBookView, request, *args, **kwargs)


class AppointmentSlotFindView(AppointmentBookingMixin, BaseGenericAPIView):
    def post(self, request, *args, **kwargs):
        started = time.monotonic()
        center = self.get_center()
        serializer = AppointmentSlotFindSerializer(
            data=request.data,
            context={"center": center, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            data = find_appointment_slots(
                center=center,
                customer_profile=validated["customer_profile"],
                service=validated["service"],
                modality=validated["modality"],
                slot_date=validated["date"],
                preferred=validated.get("preferred"),
            )
        except DjangoValidationError as exc:
            self.raise_bad_request(exc.messages[0])
        duration_seconds = time.monotonic() - started
        record_slots_duration(center.pk, duration_seconds)
        return self.send_response("Appointment slots retrieved.", data)


class AppointmentBookView(AppointmentBookingMixin, BaseGenericAPIView):
    def post(self, request, *args, **kwargs):
        started = time.monotonic()
        center = self.get_center()
        serializer = AppointmentBookSerializer(
            data=request.data,
            context={"center": center, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        assignment = get_center_service_assignment(center, validated["service"])
        if assignment is None:
            self.raise_bad_request("Service is not available at this center.")
        room = resolve_room(center, validated.get("room_id"))
        equipment = resolve_equipment(center, validated.get("equipment_id"))
        try:
            associates_payload, care_team = resolve_booking_associates(
                center, assignment, validated
            )
        except DjangoValidationError as exc:
            self.raise_bad_request(exc.messages[0])

        idempotency_key = request.headers.get("Idempotency-Key")
        payload_hash = canonical_payload_hash(request.data)
        if idempotency_key:
            existing_key = (
                AppointmentIdempotencyKey.objects.filter(
                    center=center,
                    idempotency_key=idempotency_key,
                    expires_at__gt=timezone.now(),
                )
                .select_related("appointment__care_team")
                .first()
            )
            if existing_key:
                if existing_key.payload_hash != payload_hash:
                    raise ConflictError(
                        "Idempotency key was already used with a different payload."
                    )
                detail = AppointmentDetailSerializer(existing_key.appointment).data
                return self.send_response(
                    "Appointment retrieved.",
                    detail,
                    status=200,
                )

        try:
            validate_appointment_allocation(
                center=center,
                assignment=assignment,
                modality=validated["modality"],
                start=validated["start"],
                end=validated["end"],
                associates=associates_payload,
                room=room,
                equipment=equipment,
                customer_profile=validated["customer_profile"],
            )
        except DjangoValidationError as exc:
            record_book_outcome(center.pk, "validation_error")
            self.raise_bad_request(exc.messages[0])

        try:
            with transaction.atomic():
                appointment = create_appointment_record(
                    center,
                    validated,
                    assignment,
                    room,
                    equipment,
                    request.user,
                    associates_payload,
                    care_team,
                )
                if idempotency_key:
                    AppointmentIdempotencyKey.objects.create(
                        center=center,
                        idempotency_key=idempotency_key,
                        payload_hash=payload_hash,
                        appointment=appointment,
                        expires_at=timezone.now() + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
                    )
        except IntegrityError:
            record_book_outcome(center.pk, "conflict")
            self.raise_bad_request("Slot no longer available.")

        record_book_outcome(center.pk, "success")
        invalidate_operations_cache(center.pk)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_appointment_event(
            "info",
            center_id=center.pk,
            actor_id=request.user.pk,
            action="book",
            appointment_id=appointment.pk,
            duration_ms=duration_ms,
        )
        detail = AppointmentDetailSerializer(appointment).data
        return self.send_response("Appointment booked.", detail, status=201)


class AppointmentListView(AppointmentBookingMixin, BaseListAPIView):
    serializer_class = AppointmentListSerializer
    pagination_class = None

    def get_queryset(self):
        start_date, granularity = parse_calendar_query_params(
            self.request, default_granularity=AvailabilityGranularity.WEEK
        )
        if granularity not in AvailabilityGranularity.values:
            self.raise_bad_request("Invalid granularity. Use day, week, or month.")
        query_start, query_end = resolve_query_date_range(start_date, granularity)
        range_start, range_end = datetime_range_for_dates(
            query_start,
            query_end,
            get_center_timezone_name(self.get_center()),
        )
        return (
            self.get_appointment_queryset()
            .filter(
                start_datetime__lt=range_end,
                end_datetime__gt=range_start,
            )
            .order_by("start_datetime")
        )

    def get(self, request, *args, **kwargs):
        started = time.monotonic()
        queryset = self.get_queryset()
        total_count = queryset.count()
        granularity = request.query_params.get("granularity", AvailabilityGranularity.WEEK)
        truncated = False
        if granularity in {
            AvailabilityGranularity.WEEK,
            AvailabilityGranularity.MONTH,
        } and total_count > LIST_CAP:
            truncated = True
            queryset = queryset[:LIST_CAP]
        serializer = self.get_serializer(queryset, many=True)
        data = {
            "appointments": serializer.data,
            "truncated": truncated,
            "total_count": total_count,
        }
        duration_ms = int((time.monotonic() - started) * 1000)
        log_appointment_event(
            "info",
            center_id=self.get_center().pk,
            actor_id=request.user.pk,
            action="list",
            duration_ms=duration_ms,
        )
        return self.send_response("Appointments retrieved.", data)


class AppointmentDetailView(AppointmentBookingMixin, BaseRetrieveAPIView):
    serializer_class = AppointmentDetailSerializer

    def get_object(self):
        return get_object_or_404(
            self.get_appointment_queryset(),
            "Appointment not found.",
            pk=self.kwargs["pk"],
        )

    def get(self, request, *args, **kwargs):
        appointment = self.get_object()
        data = AppointmentDetailSerializer(appointment).data
        return self.send_response("Appointment retrieved.", data)


class AppointmentLifecycleActionView(AppointmentBookingMixin, BaseGenericAPIView):
    action = None
    serializer_class = AppointmentLifecycleSerializer
    success_message = "Appointment updated."

    def get_appointment(self):
        return get_object_or_404(
            self.get_appointment_queryset(),
            "Appointment not found.",
            pk=self.kwargs["pk"],
        )

    def post(self, request, *args, **kwargs):
        started = time.monotonic()
        appointment = self.get_appointment()
        serializer = self.serializer_class(
            data=request.data,
            context={
                "appointment": appointment,
                "action": self.action,
                "request": request,
            },
        )
        serializer.is_valid(raise_exception=True)
        center = self.get_center()
        apply_status_change(appointment, self.action)
        appointment.refresh_from_db()
        audit_action = ACTION_AUDIT_MAP[self.action]
        create_audit_log(appointment, request.user, audit_action)
        record_lifecycle(center.pk, self.action, appointment.status)
        invalidate_operations_cache(center.pk)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_appointment_event(
            "info",
            center_id=center.pk,
            actor_id=request.user.pk,
            action=self.action,
            appointment_id=appointment.pk,
            duration_ms=duration_ms,
        )
        data = AppointmentDetailSerializer(appointment).data
        return self.send_response(self.success_message, data)


class AppointmentCheckInView(AppointmentLifecycleActionView):
    action = "check-in"
    success_message = "Appointment checked in."


class AppointmentStartView(AppointmentLifecycleActionView):
    action = "start"
    success_message = "Appointment started."


class AppointmentCompleteView(AppointmentLifecycleActionView):
    action = "complete"
    success_message = "Appointment completed."


class AppointmentNoShowView(AppointmentLifecycleActionView):
    action = "no-show"
    success_message = "Appointment marked as no-show."


class AppointmentMarkLateView(AppointmentBookingMixin, BaseGenericAPIView):
    def post(self, request, *args, **kwargs):
        started = time.monotonic()
        appointment = get_object_or_404(
            self.get_appointment_queryset(),
            "Appointment not found.",
            pk=self.kwargs["pk"],
        )
        serializer = AppointmentMarkLateSerializer(
            data=request.data,
            context={"appointment": appointment, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        center = self.get_center()
        apply_status_change(appointment, "mark-late")
        appointment.is_late = True
        appointment.late_by = serializer.validated_data["late_by"]
        appointment.save(update_fields=["is_late", "late_by", "updated_at"])
        create_audit_log(
            appointment,
            request.user,
            AppointmentAuditAction.MARK_LATE,
            note=f"Late by {appointment.late_by} minutes",
        )
        record_lifecycle(center.pk, "mark-late", appointment.status)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_appointment_event(
            "info",
            center_id=center.pk,
            actor_id=request.user.pk,
            action="mark-late",
            appointment_id=appointment.pk,
            duration_ms=duration_ms,
        )
        data = AppointmentDetailSerializer(appointment).data
        return self.send_response("Appointment marked as late.", data)


class AppointmentCancelView(AppointmentBookingMixin, BaseGenericAPIView):
    def post(self, request, *args, **kwargs):
        started = time.monotonic()
        appointment = get_object_or_404(
            self.get_appointment_queryset(),
            "Appointment not found.",
            pk=self.kwargs["pk"],
        )
        serializer = AppointmentCancelSerializer(
            data=request.data,
            context={"appointment": appointment, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        center = self.get_center()
        appointment.cancel_reason = serializer.validated_data["reason"]
        appointment.save(update_fields=["cancel_reason", "updated_at"])
        apply_status_change(appointment, "cancel")
        appointment.refresh_from_db()
        resolve_exceptions_for_appointment(
            appointment,
            ExceptionResolution.CANCELLED,
        )
        create_audit_log(
            appointment,
            request.user,
            AppointmentAuditAction.CANCEL,
            note=appointment.cancel_reason,
        )
        record_lifecycle(center.pk, "cancel", appointment.status)
        invalidate_operations_cache(center.pk)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_appointment_event(
            "info",
            center_id=center.pk,
            actor_id=request.user.pk,
            action="cancel",
            appointment_id=appointment.pk,
            duration_ms=duration_ms,
        )
        data = AppointmentDetailSerializer(appointment).data
        return self.send_response("Appointment cancelled.", data)


class AppointmentRescheduleView(AppointmentBookingMixin, BaseGenericAPIView):
    def post(self, request, *args, **kwargs):
        started = time.monotonic()
        appointment = get_object_or_404(
            self.get_appointment_queryset(),
            "Appointment not found.",
            pk=self.kwargs["pk"],
        )
        center = self.get_center()
        serializer = AppointmentRescheduleSerializer(
            data=request.data,
            context={
                "center": center,
                "appointment": appointment,
                "request": request,
            },
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        assignment = get_center_service_assignment(center, validated["service"])
        if assignment is None:
            self.raise_bad_request("Service is not available at this center.")
        room = resolve_room(center, validated.get("room_id"))
        equipment = resolve_equipment(center, validated.get("equipment_id"))
        try:
            associates_payload, care_team = resolve_booking_associates(
                center, assignment, validated
            )
        except DjangoValidationError as exc:
            self.raise_bad_request(exc.messages[0])

        try:
            validate_appointment_allocation(
                center=center,
                assignment=assignment,
                modality=validated["modality"],
                start=validated["start"],
                end=validated["end"],
                associates=associates_payload,
                room=room,
                equipment=equipment,
                customer_profile=validated["customer_profile"],
                exclude_appointment=appointment,
            )
        except DjangoValidationError as exc:
            self.raise_bad_request(exc.messages[0])

        buffer_before = assignment.buffer_before
        buffer_after = assignment.buffer_after
        exclusive_start, exclusive_end = compute_exclusive_bounds(
            validated["start"],
            validated["end"],
            buffer_before,
            buffer_after,
        )

        try:
            with transaction.atomic():
                AppointmentHistory.objects.create(
                    appointment=appointment,
                    previous_start_datetime=appointment.start_datetime,
                    previous_end_datetime=appointment.end_datetime,
                    previous_exclusive_start_datetime=appointment.exclusive_start_datetime,
                    previous_exclusive_end_datetime=appointment.exclusive_end_datetime,
                    actor=request.user,
                )
                appointment.start_datetime = validated["start"]
                appointment.end_datetime = validated["end"]
                appointment.duration_minutes = assignment.duration
                appointment.buffer_before_minutes = buffer_before
                appointment.buffer_after_minutes = buffer_after
                appointment.exclusive_start_datetime = exclusive_start
                appointment.exclusive_end_datetime = exclusive_end
                appointment.modality = validated["modality"]
                appointment.room = room
                appointment.equipment = equipment
                appointment.care_team = care_team
                appointment.status = AppointmentStatus.CONFIRMED
                appointment.save()
                appointment.associate_links.all().delete()
                create_appointment_associates(
                    appointment,
                    associates_payload,
                    exclusive_start,
                    exclusive_end,
                )
                sync_associate_status_snapshots(appointment)
                create_audit_log(
                    appointment,
                    request.user,
                    AppointmentAuditAction.RESCHEDULE,
                )
        except IntegrityError:
            self.raise_bad_request("Slot no longer available.")

        resolve_exceptions_for_appointment(
            appointment,
            ExceptionResolution.RESCHEDULED,
        )
        detect_exceptions_for_appointment(appointment)
        record_lifecycle(center.pk, "reschedule", appointment.status)
        invalidate_operations_cache(center.pk)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_appointment_event(
            "info",
            center_id=center.pk,
            actor_id=request.user.pk,
            action="reschedule",
            appointment_id=appointment.pk,
            duration_ms=duration_ms,
        )
        data = AppointmentDetailSerializer(appointment).data
        return self.send_response("Appointment rescheduled.", data)
