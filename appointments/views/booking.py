import hashlib
import json
import re
import time

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import F, Q, Value
from django.db.models.functions import Concat
from django.utils import timezone
from rest_framework.exceptions import APIException

from appointments.mixins import CenterAppointmentsMixin
from appointments.models import AppointmentIdempotencyKey
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
from appointments.utils.calendar import get_center_timezone_name, parse_calendar_query_params
from appointments.utils.constants import AppointmentStatus, AvailabilityGranularity
from appointments.utils.operations import invalidate_operations_cache
from appointments.utils.intervals import datetime_range_for_dates, resolve_query_date_range
from appointments.utils.metrics import (
    log_appointment_event,
    record_book_outcome,
    record_lifecycle,
    record_slots_duration,
)
from appointments.utils.scheduling import (
    find_appointment_slots,
    resolve_booking_combo,
)
from core.utils.db.functions import ExtractPartText
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import BaseGenericAPIView, BaseListAPIView, BaseRetrieveAPIView
from inventory.models import Equipment, Room

LIST_CAP = 500
APPOINTMENT_CODE_CONSTRAINT = "uniq_appointment_code_per_center"
IDEMPOTENCY_KEY_CONSTRAINT = "uniq_appointment_idempotency_key_per_center"
UUID_QUERY_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
APPOINTMENT_LIST_UUID_FILTERS = (
    ("service_id", "service_id"),
    ("room_id", "room_id"),
    ("equipment_id", "equipment_id"),
    ("equipment_type_id", "equipment__equipment_type_id"),
    ("care_team_id", "care_team_id"),
)
INVALID_APPOINTMENT_STATUS = (
    "Invalid status. Use confirmed, checked_in, in_progress, "
    "completed, cancelled, or no_show."
)


def parse_optional_uuid_query(query_params, param_name):
    raw_value = (query_params.get(param_name) or "").strip()
    if not raw_value:
        return None, None
    if UUID_QUERY_PATTERN.fullmatch(raw_value) is None:
        return None, f"Invalid {param_name}."
    return raw_value, None


def appointment_list_uses_date_window(query_params):
    search_params = (query_params.get("search") or "").strip()
    start_raw = (query_params.get("start") or "").strip()
    return not search_params or bool(start_raw)


def apply_appointment_list_search(queryset, query_params):
    search_params = (query_params.get("search") or "").strip()
    if not search_params:
        return queryset
    queryset = queryset.annotate(
        customer_full_name=Concat(
            F("customer_profile__first_name"),
            Value(" "),
            F("customer_profile__last_name"),
        ),
        customer_national_phone=ExtractPartText(
            F("customer_profile__customer__user__phone"),
            Value("-"),
            Value("-1"),
        ),
    )
    search = Q()
    search |= Q(customer_full_name__istartswith=search_params)
    search |= Q(customer_full_name__icontains=search_params)
    search |= Q(customer_profile__first_name__istartswith=search_params)
    search |= Q(customer_profile__last_name__istartswith=search_params)
    search |= Q(
        customer_profile__customer__contact_email__istartswith=search_params
    )
    search |= Q(
        customer_profile__customer__contact_email__icontains=search_params
    )
    search |= Q(customer_national_phone__istartswith=search_params)
    search |= Q(code__icontains=search_params)
    search |= Q(service__name__icontains=search_params)
    return queryset.filter(search)


def apply_appointment_list_filters(queryset, query_params):
    filter_kwargs = {}
    for param_name, field_name in APPOINTMENT_LIST_UUID_FILTERS:
        value, error = parse_optional_uuid_query(query_params, param_name)
        if error:
            return None, error
        if value is not None:
            filter_kwargs[field_name] = value
    if filter_kwargs:
        queryset = queryset.filter(**filter_kwargs)

    status = (query_params.get("status") or "").strip()
    if status:
        if status not in AppointmentStatus.values:
            return None, INVALID_APPOINTMENT_STATUS
        queryset = queryset.filter(status=status)

    queryset = apply_appointment_list_search(queryset, query_params)

    associate_id, error = parse_optional_uuid_query(query_params, "associate_id")
    if error:
        return None, error
    role_id, error = parse_optional_uuid_query(query_params, "role_id")
    if error:
        return None, error

    if associate_id is not None and role_id is not None:
        queryset = queryset.filter(
            associate_links__associate_id=associate_id,
            associate_links__role_id=role_id,
        ).distinct()
    elif associate_id is not None:
        queryset = queryset.filter(
            associate_links__associate_id=associate_id
        ).distinct()
    elif role_id is not None:
        queryset = queryset.filter(associate_links__role_id=role_id).distinct()

    return queryset, None


def appointment_list_should_cap(query_params, total_count):
    if total_count <= LIST_CAP:
        return False
    if not appointment_list_uses_date_window(query_params):
        return True
    granularity = query_params.get("granularity", AvailabilityGranularity.WEEK)
    return granularity in {
        AvailabilityGranularity.WEEK,
        AvailabilityGranularity.MONTH,
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


def integrity_error_constraint_name(error):
    diagnostic = getattr(error.__cause__, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    if constraint_name:
        return constraint_name
    return str(error)


def integrity_error_matches_constraint(error, constraint_name):
    return constraint_name in integrity_error_constraint_name(error)


def appointment_write_integrity_detail(error):
    if integrity_error_matches_constraint(error, APPOINTMENT_CODE_CONSTRAINT):
        return "Appointment code already exists."
    return "Slot no longer available."


def get_appointment_idempotency_key(center, idempotency_key, unexpired_only=False):
    queryset = AppointmentIdempotencyKey.objects.filter(
        center=center,
        idempotency_key=idempotency_key,
    ).select_related("appointment__care_team")
    if unexpired_only:
        queryset = queryset.filter(expires_at__gt=timezone.now())
    return queryset.first()


def raise_idempotency_payload_conflict(existing_key, payload_hash):
    if existing_key.payload_hash != payload_hash:
        raise ConflictError(
            "Idempotency key was already used with a different payload."
        )


def resolve_room(center, room_id):
    if room_id is None:
        return None
    room = Room.objects.filter(center=center, is_active=True, pk=room_id).first()
    if room is None:
        raise DjangoValidationError("Invalid room for this center.")
    return room


def resolve_equipment(center, equipment_id):
    if equipment_id is None:
        return None
    equipment = Equipment.objects.filter(
        center=center, is_active=True, pk=equipment_id
    ).first()
    if equipment is None:
        raise DjangoValidationError("Invalid equipment for this center.")
    return equipment


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
        assignment = validated["assignment"]
        try:
            combo = resolve_booking_combo(
                center=center,
                assignment=assignment,
                modality=validated["modality"],
                preferred=validated.get("preferred"),
                start=validated["start"],
                end=validated["end"],
                associates=build_associate_payload(validated.get("associates") or []),
                room=resolve_room(center, validated.get("room_id")),
                equipment=resolve_equipment(center, validated.get("equipment_id")),
                customer_profile=validated["customer_profile"],
            )
        except DjangoValidationError as exc:
            record_book_outcome(center.pk, "validation_error")
            self.raise_bad_request(exc.messages[0])

        associates_payload = combo["associates"]
        room = combo["room"]
        equipment = combo["equipment"]
        care_team = combo["care_team"]

        idempotency_key = request.headers.get("Idempotency-Key")
        payload_hash = canonical_payload_hash(request.data)
        if idempotency_key:
            existing_key = get_appointment_idempotency_key(
                center,
                idempotency_key,
                unexpired_only=True,
            )
            if existing_key:
                raise_idempotency_payload_conflict(existing_key, payload_hash)
                detail = AppointmentDetailSerializer(existing_key.appointment).data
                return self.send_response(
                    "Appointment retrieved.",
                    detail,
                    status=200,
                )

        try:
            serializer.save(
                assignment=assignment,
                room=room,
                equipment=equipment,
                associates_payload=associates_payload,
                care_team=care_team,
                actor=request.user,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
            )
        except IntegrityError as error:
            if integrity_error_matches_constraint(error, IDEMPOTENCY_KEY_CONSTRAINT):
                existing_key = get_appointment_idempotency_key(
                    center,
                    idempotency_key,
                )
                if existing_key:
                    raise_idempotency_payload_conflict(existing_key, payload_hash)
                    detail = AppointmentDetailSerializer(
                        existing_key.appointment
                    ).data
                    return self.send_response(
                        "Appointment retrieved.",
                        detail,
                        status=200,
                    )
            record_book_outcome(center.pk, "conflict")
            self.raise_bad_request(appointment_write_integrity_detail(error))

        appointment = serializer.instance
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
        queryset = self.get_appointment_queryset()
        if appointment_list_uses_date_window(self.request.query_params):
            start_date, granularity = parse_calendar_query_params(
                self.request, default_granularity=AvailabilityGranularity.WEEK
            )
            if granularity not in AvailabilityGranularity.values:
                self.raise_bad_request(
                    "Invalid granularity. Use day, week, or month."
                )
            query_start, query_end = resolve_query_date_range(
                start_date, granularity
            )
            range_start, range_end = datetime_range_for_dates(
                query_start,
                query_end,
                get_center_timezone_name(self.get_center()),
            )
            queryset = queryset.filter(
                start_datetime__lt=range_end,
                end_datetime__gt=range_start,
            ).order_by("start_datetime")
        else:
            queryset = queryset.order_by("-start_datetime")
        queryset, error = apply_appointment_list_filters(
            queryset, self.request.query_params
        )
        if error:
            self.raise_bad_request(error)
        return queryset

    def get(self, request, *args, **kwargs):
        started = time.monotonic()
        queryset = self.get_queryset()
        total_count = queryset.count()
        truncated = False
        if appointment_list_should_cap(request.query_params, total_count):
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
            appointment,
            data=request.data,
            context={
                "appointment": appointment,
                "action": self.action,
                "request": request,
            },
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(actor=request.user)
        appointment = serializer.instance
        center = self.get_center()
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
            appointment,
            data=request.data,
            context={"appointment": appointment, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(actor=request.user)
        appointment = serializer.instance
        center = self.get_center()
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
            appointment,
            data=request.data,
            context={"appointment": appointment, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(actor=request.user)
        appointment = serializer.instance
        center = self.get_center()
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
            appointment,
            data=request.data,
            context={
                "center": center,
                "appointment": appointment,
                "request": request,
            },
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        assignment = validated["assignment"]
        try:
            combo = resolve_booking_combo(
                center=center,
                assignment=assignment,
                modality=validated["modality"],
                preferred=validated.get("preferred"),
                start=validated["start"],
                end=validated["end"],
                associates=build_associate_payload(validated.get("associates") or []),
                room=resolve_room(center, validated.get("room_id")),
                equipment=resolve_equipment(center, validated.get("equipment_id")),
                customer_profile=validated["customer_profile"],
                exclude_appointment=appointment,
            )
        except DjangoValidationError as exc:
            self.raise_bad_request(exc.messages[0])

        try:
            serializer.save(
                assignment=assignment,
                room=combo["room"],
                equipment=combo["equipment"],
                associates_payload=combo["associates"],
                care_team=combo["care_team"],
                actor=request.user,
            )
        except IntegrityError as error:
            self.raise_bad_request(appointment_write_integrity_detail(error))

        appointment = serializer.instance
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
