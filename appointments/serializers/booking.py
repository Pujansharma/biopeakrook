from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.associates.models import Associate, AssociateRole
from accounts.centers.serializers import MinimumCenterSerializer
from accounts.customers.models import CustomerProfile
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from appointments.models import (
    Appointment,
    AppointmentAssociate,
    AppointmentAuditLog,
    AppointmentHistory,
    AppointmentIdempotencyKey,
)
from appointments.utils.codes import generate_appointment_code
from appointments.utils.calendar import center_local_date
from appointments.utils.constants import (
    AppointmentAuditAction,
    AppointmentStatus,
    ExceptionResolution,
)
from appointments.utils.exceptions import (
    detect_exceptions_for_appointment,
    resolve_exceptions_for_appointment,
)
from appointments.utils.scheduling import (
    HEALTH_COACH_ID_REJECT_MESSAGE,
    PREFERRED_REQUIRED_MESSAGE,
    SPECIALTY_ID_DUPLICATE_MESSAGE,
    SPECIALTY_ID_EMPTY_MESSAGE,
    SPECIALTY_ID_TYPE_MESSAGE,
    compute_exclusive_bounds,
    get_center_service_assignment,
    validate_preferred_combo,
)
from appointments.utils.redemption import (
    cancel_appointment_redemption,
    complete_appointment_redemption,
    ensure_customer_slot_within_therapy_programs,
    ensure_program_covers_appointment_date,
    resolve_bookable_therapy_program_service,
    schedule_appointment_redemption,
)
from appointments.utils.transitions import (
    apply_status_change,
    sync_associate_status_snapshots,
    validate_transition,
)
from core.utils.constants import AppointmentModes
from core.utils.serializers import BaseSerializer
from integrations.communications import (
    schedule_queue_appointment_cancelled,
    schedule_queue_appointment_confirmed,
    schedule_queue_appointment_no_show,
    schedule_queue_appointment_rescheduled,
)
from programs.services.models import Service

IDEMPOTENCY_TTL_HOURS = 24
BOOKING_RESOURCE_KEYS = (
    "doctor_id",
    "specialty_id",
    "care_team_id",
    "room_id",
    "equipment_id",
)
CUSTOMER_PROFILE_NOT_OWNED_MESSAGE = (
    "Customer profile does not belong to this account."
)
CUSTOMER_PREFERRED_FORBIDDEN_MESSAGE = (
    "Customers cannot send preferred. Slots are auto-assigned."
)
CUSTOMER_PROGRAM_SERVICE_REQUIRED_MESSAGE = (
    "program_service_id is required for customers."
)
STAFF_PROGRAM_SERVICE_FORBIDDEN_MESSAGE = (
    "program_service_id is not allowed when booking as staff."
)
PROGRAM_SERVICE_MISMATCH_MESSAGE = (
    "program_service_id does not match this appointment."
)
CUSTOMER_BOOKING_WINDOW_DAYS = 7
CUSTOMER_BOOKING_DATE_MESSAGE = (
    "Date must be between tomorrow and 7 days from today."
)


def ensure_customer_booking_date(slot_date, center, field_name="date"):
    """Customer slots/book/reschedule: tomorrow .. today+7 (center local date)."""
    today = center_local_date(center)
    min_date = today + timedelta(days=1)
    max_date = today + timedelta(days=CUSTOMER_BOOKING_WINDOW_DAYS)
    if slot_date < min_date or slot_date > max_date:
        raise serializers.ValidationError(
            {field_name: [CUSTOMER_BOOKING_DATE_MESSAGE]}
        )


class SpecialtyIdField(serializers.Field):
    """Book/reschedule only: one UUID or a non-empty UUID array → list[str]."""

    def to_internal_value(self, data):
        if data is None:
            return None
        uuid_field = serializers.UUIDField()
        if isinstance(data, list):
            if not data:
                raise serializers.ValidationError(SPECIALTY_ID_EMPTY_MESSAGE)
            specialty_ids = []
            for item in data:
                specialty_ids.append(str(uuid_field.to_internal_value(item)))
            if len(specialty_ids) != len(set(specialty_ids)):
                raise serializers.ValidationError(SPECIALTY_ID_DUPLICATE_MESSAGE)
            return specialty_ids
        try:
            return [str(uuid_field.to_internal_value(data))]
        except serializers.ValidationError as error:
            if isinstance(data, (dict, tuple)):
                raise serializers.ValidationError(SPECIALTY_ID_TYPE_MESSAGE)
            raise error

    def to_representation(self, value):
        if value is None:
            return None
        if isinstance(value, list):
            if len(value) == 1:
                return value[0]
            return value
        return value

LIFECYCLE_AUDIT_MAP = {
    "check-in": AppointmentAuditAction.CHECK_IN,
    "start": AppointmentAuditAction.START,
    "mark-late": AppointmentAuditAction.MARK_LATE,
    "complete": AppointmentAuditAction.COMPLETE,
    "no-show": AppointmentAuditAction.NO_SHOW,
    "cancel": AppointmentAuditAction.CANCEL,
    "reschedule": AppointmentAuditAction.RESCHEDULE,
}


def resolve_center_customer_profile(center, customer_profile_id):
    customer_profile = (
        CustomerProfile.objects.filter(
            pk=customer_profile_id,
            is_active=True,
            center_assignments__center=center,
            center_assignments__is_active=True,
        )
        .distinct()
        .first()
    )
    if customer_profile is None:
        raise serializers.ValidationError(
            {"customer_profile_id": ["Invalid customer profile for this center."]}
        )
    return customer_profile


def ensure_request_owns_customer_profile(request, customer_profile):
    if request is None:
        return
    if get_user_account_type(request.user) != UserType.CUSTOMER:
        return
    if (
        not hasattr(request.user, "customer")
        or customer_profile.customer_id != request.user.pk
    ):
        raise serializers.ValidationError(
            {"customer_profile_id": [CUSTOMER_PROFILE_NOT_OWNED_MESSAGE]}
        )


def resolve_center_service(center, service_id):
    service = (
        Service.objects.filter(
            pk=service_id,
            is_active=True,
            center_assignments__center=center,
            center_assignments__is_active=True,
        )
        .distinct()
        .first()
    )
    if service is None:
        raise serializers.ValidationError(
            {"service_id": ["Invalid service for this center."]}
        )
    return service


def create_audit_log(appointment, actor, action, note=""):
    AppointmentAuditLog.objects.create(
        appointment=appointment,
        actor=actor,
        action=action,
        note=note,
    )


def create_appointment_associates(
    appointment, associates_payload, exclusive_start, exclusive_end
):
    if not associates_payload:
        return
    associates_by_id = {
        str(associate.pk): associate
        for associate in Associate.objects.filter(
            pk__in=[entry["associate_id"] for entry in associates_payload]
        )
    }
    roles_by_id = {
        str(role.pk): role
        for role in AssociateRole.objects.filter(
            pk__in=[entry["role_id"] for entry in associates_payload]
        )
    }
    for entry in associates_payload:
        AppointmentAssociate.objects.create(
            appointment=appointment,
            associate=associates_by_id[str(entry["associate_id"])],
            role=roles_by_id[str(entry["role_id"])],
            exclusive_start_datetime=exclusive_start,
            exclusive_end_datetime=exclusive_end,
            appointment_status=appointment.status,
        )


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
        program_service=validated_data.get("program_service"),
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
        notes=validated_data.get("notes"),
        created_by=actor,
    )
    create_appointment_associates(
        appointment,
        associates_payload,
        exclusive_start,
        exclusive_end,
    )
    create_audit_log(appointment, actor, AppointmentAuditAction.CREATE)
    schedule_appointment_redemption(appointment, actor)
    return appointment


class AppointmentPreferredSerializer(BaseSerializer):
    doctor_id = serializers.UUIDField(required=False)
    specialty_id = serializers.UUIDField(required=False)
    room_id = serializers.UUIDField(required=False)
    equipment_id = serializers.UUIDField(required=False)
    care_team_id = serializers.UUIDField(required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "health_coach_id" in data:
            raise serializers.ValidationError(HEALTH_COACH_ID_REJECT_MESSAGE)
        return super().to_internal_value(data)


class AppointmentSlotFindSerializer(BaseSerializer):
    customer_profile_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    modality = serializers.ChoiceField(choices=AppointmentModes.choices)
    date = serializers.DateField()
    program_service_id = serializers.UUIDField(required=False, allow_null=True)
    preferred = AppointmentPreferredSerializer(required=False, allow_null=True)

    def validate_modality(self, value):
        if value == AppointmentModes.BOTH:
            raise serializers.ValidationError(
                "Modality must be virtual or in_person."
            )
        return value

    def validate_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("Date cannot be in the past.")
        return value

    def validate(self, attrs):
        center = self.context["center"]
        request = self.context.get("request")
        customer_profile = resolve_center_customer_profile(
            center, attrs["customer_profile_id"]
        )
        ensure_request_owns_customer_profile(request, customer_profile)
        service = resolve_center_service(center, attrs["service_id"])
        attrs["customer_profile"] = customer_profile
        attrs["service"] = service
        attrs["center"] = center

        account_type = (
            get_user_account_type(request.user)
            if request is not None
            else None
        )
        preferred_in_payload = (
            isinstance(self.initial_data, dict) and "preferred" in self.initial_data
        )
        if account_type == UserType.CUSTOMER:
            if preferred_in_payload:
                raise serializers.ValidationError(
                    {"preferred": [CUSTOMER_PREFERRED_FORBIDDEN_MESSAGE]}
                )
            ensure_customer_booking_date(
                attrs["date"], attrs["center"], field_name="date"
            )
            ensure_customer_slot_within_therapy_programs(
                customer_profile,
                service,
                attrs["date"],
                program_service_id=attrs.get("program_service_id"),
            )
            attrs["preferred"] = None
            attrs["auto_assign"] = True
            return attrs

        preferred = normalize_preferred(
            attrs.get("preferred"),
            modality=attrs["modality"],
            required=True,
        )
        attrs["preferred"] = preferred
        attrs["auto_assign"] = False
        return attrs


def preferred_from_booking_attrs(attrs):
    preferred = {}
    for key in BOOKING_RESOURCE_KEYS:
        value = attrs.get(key)
        if value is None:
            continue
        if key == "specialty_id" and isinstance(value, list):
            preferred[key] = [str(item) for item in value]
            continue
        preferred[key] = str(value)
    return preferred


def preferred_combo_error_payload(error, nest_under=None):
    if hasattr(error, "error_dict"):
        payload = error.message_dict
    else:
        payload = error.messages
    if nest_under is not None:
        return {nest_under: payload}
    return payload


def normalize_preferred(preferred, modality=None, required=False):
    if preferred is None:
        if required:
            raise serializers.ValidationError(
                {"preferred": [PREFERRED_REQUIRED_MESSAGE]}
            )
        return None
    if isinstance(preferred, dict) and "health_coach_id" in preferred:
        raise serializers.ValidationError(
            {"preferred": [HEALTH_COACH_ID_REJECT_MESSAGE]}
        )
    normalized_preferred = {}
    for key, value in preferred.items():
        if value is not None:
            normalized_preferred[key] = str(value)
    if not normalized_preferred:
        if required:
            raise serializers.ValidationError(
                {"preferred": [PREFERRED_REQUIRED_MESSAGE]}
            )
        return None
    if modality is not None:
        try:
            validate_preferred_combo(normalized_preferred, modality)
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                preferred_combo_error_payload(error, nest_under="preferred")
            )
    return normalized_preferred


class AppointmentBookSerializer(BaseSerializer):
    customer_profile_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    program_service_id = serializers.UUIDField(required=False, allow_null=True)
    modality = serializers.ChoiceField(choices=AppointmentModes.choices)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    doctor_id = serializers.UUIDField(required=False, allow_null=True)
    specialty_id = SpecialtyIdField(required=False, allow_null=True)
    care_team_id = serializers.UUIDField(required=False, allow_null=True)
    room_id = serializers.UUIDField(required=False, allow_null=True)
    equipment_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "health_coach_id" in data:
            raise serializers.ValidationError(HEALTH_COACH_ID_REJECT_MESSAGE)
        return super().to_internal_value(data)

    def validate_modality(self, value):
        if value == AppointmentModes.BOTH:
            raise serializers.ValidationError(
                "Modality must be virtual or in_person."
            )
        return value

    def apply_program_service_rules(self, attrs):
        request = self.context.get("request")
        program_service_id = attrs.get("program_service_id")
        account_type = (
            get_user_account_type(request.user)
            if request is not None
            else None
        )
        attrs["program_service"] = None
        if account_type == UserType.CUSTOMER:
            if program_service_id is None:
                raise serializers.ValidationError(
                    {"program_service_id": [CUSTOMER_PROGRAM_SERVICE_REQUIRED_MESSAGE]}
                )
            therapy_program_service = resolve_bookable_therapy_program_service(
                program_service_id,
                attrs["customer_profile"],
                attrs["service"],
                attrs["center"],
                appointment_date=center_local_date(
                    attrs["center"], attrs["start"]
                ),
            )
            attrs["program_service"] = therapy_program_service.program_service
        elif account_type in {UserType.ADMIN, UserType.ASSOCIATE}:
            if program_service_id is not None:
                raise serializers.ValidationError(
                    {"program_service_id": [STAFF_PROGRAM_SERVICE_FORBIDDEN_MESSAGE]}
                )
        return attrs

    def validate(self, attrs):
        center = self.context["center"]
        request = self.context.get("request")
        customer_profile = resolve_center_customer_profile(
            center, attrs["customer_profile_id"]
        )
        ensure_request_owns_customer_profile(request, customer_profile)
        service = resolve_center_service(center, attrs["service_id"])
        attrs["customer_profile"] = customer_profile
        attrs["service"] = service
        attrs["center"] = center
        attrs = self.apply_program_service_rules(attrs)
        preferred = preferred_from_booking_attrs(attrs)
        try:
            validate_preferred_combo(preferred, attrs["modality"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(preferred_combo_error_payload(error))
        attrs["preferred"] = preferred
        assignment = get_center_service_assignment(center, service)
        if assignment is None:
            raise serializers.ValidationError(
                "Service is not available at this center."
            )
        attrs["assignment"] = assignment
        if attrs["start"] < timezone.now():
            raise serializers.ValidationError("Date cannot be in the past.")
        account_type = (
            get_user_account_type(request.user)
            if request is not None
            else None
        )
        if account_type == UserType.CUSTOMER:
            ensure_customer_booking_date(
                center_local_date(center, attrs["start"]),
                center,
                field_name="start",
            )
        return attrs

    def create(self, validated_data):
        assignment = validated_data.pop("assignment")
        room = validated_data.pop("room")
        equipment = validated_data.pop("equipment")
        associates_payload = validated_data.pop("associates_payload")
        care_team = validated_data.pop("care_team")
        actor = validated_data.pop("actor")
        idempotency_key = validated_data.pop("idempotency_key", None)
        payload_hash = validated_data.pop("payload_hash", None)
        for key in (
            "preferred",
            "customer_profile_id",
            "service_id",
            "program_service_id",
            *BOOKING_RESOURCE_KEYS,
        ):
            validated_data.pop(key, None)
        center = self.context["center"]
        with transaction.atomic():
            appointment = create_appointment_record(
                center,
                validated_data,
                assignment,
                room,
                equipment,
                actor,
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
            schedule_queue_appointment_confirmed(appointment)
        return appointment


class AppointmentCustomerNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.SerializerMethodField()

    def get_name(self, obj):
        parts = [obj.first_name or "", obj.last_name or ""]
        return " ".join(part for part in parts if part).strip() or str(obj.pk)


class AppointmentServiceNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.CharField()


class AppointmentAssociateNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="associate.pk")
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    def get_name(self, obj):
        user = obj.associate.user
        parts = [user.first_name or "", user.last_name or ""]
        return " ".join(part for part in parts if part).strip() or str(obj.associate.pk)

    def get_role(self, obj):
        return {
            "id": str(obj.role.pk),
            "name": obj.role.name,
        }


class AppointmentRoomNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.CharField()


class AppointmentEquipmentNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.CharField()


class AppointmentCareTeamNestedSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    name = serializers.CharField()


class AppointmentListSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk")
    code = serializers.CharField()
    start = serializers.DateTimeField(source="start_datetime")
    end = serializers.DateTimeField(source="end_datetime")
    status = serializers.CharField()
    modality = serializers.CharField()
    is_late = serializers.BooleanField()
    late_by = serializers.IntegerField(allow_null=True)
    has_open_exception = serializers.BooleanField()
    customer = AppointmentCustomerNestedSerializer(source="customer_profile")
    service = AppointmentServiceNestedSerializer()
    program_service_id = serializers.UUIDField(allow_null=True)
    care_team = AppointmentCareTeamNestedSerializer(allow_null=True)
    associates = AppointmentAssociateNestedSerializer(
        source="associate_links", many=True
    )
    room = AppointmentRoomNestedSerializer(allow_null=True)
    equipment = AppointmentEquipmentNestedSerializer(allow_null=True)
    center = MinimumCenterSerializer()
    notes = serializers.CharField(allow_null=True)
    google_meet_link = serializers.URLField(allow_null=True)


class AppointmentDetailSerializer(AppointmentListSerializer):
    duration_minutes = serializers.IntegerField()
    buffer_before_minutes = serializers.IntegerField()
    buffer_after_minutes = serializers.IntegerField()
    exclusive_start = serializers.DateTimeField(source="exclusive_start_datetime")
    exclusive_end = serializers.DateTimeField(source="exclusive_end_datetime")
    cancel_reason = serializers.CharField()
    exception_resolution_hint = serializers.SerializerMethodField(
        help_text=(
            "Open-exception resolve guidance. Cancel and reschedule remain "
            "available through checked_in. In-progress exceptions can only "
            "be acknowledged."
        ),
    )
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def get_exception_resolution_hint(self, obj):
        if not obj.has_open_exception:
            return None
        if obj.status == AppointmentStatus.IN_PROGRESS:
            return (
                "In-progress exceptions can only be acknowledged. "
                "Cancel and reschedule are unavailable after the session starts."
            )
        return (
            "Resolve open exceptions by cancelling, rescheduling, "
            "or acknowledging."
        )


class AppointmentCancelSerializer(BaseSerializer):
    reason = serializers.CharField(max_length=500)

    def validate(self, attrs):
        appointment = self.context["appointment"]
        validate_transition(appointment.status, "cancel")
        return attrs

    def update(self, instance, validated_data):
        actor = validated_data.pop("actor")
        with transaction.atomic():
            instance.cancel_reason = validated_data["reason"]
            instance.save(update_fields=["cancel_reason", "updated_at"])
            apply_status_change(instance, "cancel")
            instance.refresh_from_db()
            cancel_appointment_redemption(instance, actor)
            resolve_exceptions_for_appointment(
                instance,
                ExceptionResolution.CANCELLED,
            )
            create_audit_log(
                instance,
                actor,
                AppointmentAuditAction.CANCEL,
                note=instance.cancel_reason,
            )
            schedule_queue_appointment_cancelled(instance)
        return instance


class AppointmentMarkLateSerializer(BaseSerializer):
    late_by = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        appointment = self.context["appointment"]
        validate_transition(appointment.status, "mark-late")
        return attrs

    def update(self, instance, validated_data):
        actor = validated_data.pop("actor")
        with transaction.atomic():
            apply_status_change(instance, "mark-late")
            instance.is_late = True
            instance.late_by = validated_data["late_by"]
            instance.save(update_fields=["is_late", "late_by", "updated_at"])
            create_audit_log(
                instance,
                actor,
                AppointmentAuditAction.MARK_LATE,
                note=f"Late by {instance.late_by} minutes",
            )
        return instance


class AppointmentRescheduleSerializer(AppointmentBookSerializer):
    def apply_program_service_rules(self, attrs):
        request = self.context.get("request")
        program_service_id = attrs.get("program_service_id")
        account_type = (
            get_user_account_type(request.user)
            if request is not None
            else None
        )
        attrs["program_service"] = None
        appointment = self.context["appointment"]
        linked_program = None
        if account_type == UserType.CUSTOMER:
            # Customer UI only lists therapy-linked appts (never staff walk-ins).
            if program_service_id is None:
                raise serializers.ValidationError(
                    {"program_service_id": [CUSTOMER_PROGRAM_SERVICE_REQUIRED_MESSAGE]}
                )
            if (
                appointment.program_service is None
                or program_service_id != appointment.program_service.pk
            ):
                raise serializers.ValidationError(
                    {"program_service_id": [PROGRAM_SERVICE_MISMATCH_MESSAGE]}
                )
            linked_program = appointment.program_service.program
        elif account_type in {UserType.ADMIN, UserType.ASSOCIATE}:
            if program_service_id is not None:
                raise serializers.ValidationError(
                    {"program_service_id": [STAFF_PROGRAM_SERVICE_FORBIDDEN_MESSAGE]}
                )
            if appointment.program_service is not None:
                linked_program = appointment.program_service.program
        if linked_program is not None:
            ensure_program_covers_appointment_date(
                linked_program,
                center_local_date(attrs["center"], attrs["start"]),
                field_name="start",
            )
        return attrs

    def validate(self, attrs):
        attrs = super().validate(attrs)
        appointment = self.context["appointment"]
        validate_transition(appointment.status, "reschedule")
        if attrs["customer_profile"].pk != appointment.customer_profile.pk:
            raise serializers.ValidationError(
                {"customer_profile_id": ["Cannot change the customer on a reschedule."]}
            )
        if attrs["service"].pk != appointment.service.pk:
            raise serializers.ValidationError(
                {"service_id": ["Cannot change the service on a reschedule."]}
            )
        return attrs

    def update(self, instance, validated_data):
        assignment = validated_data.pop("assignment")
        room = validated_data.pop("room")
        equipment = validated_data.pop("equipment")
        associates_payload = validated_data.pop("associates_payload")
        care_team = validated_data.pop("care_team")
        actor = validated_data.pop("actor")
        validated_data.pop("preferred", None)
        validated_data.pop("program_service", None)
        for key in ("customer_profile_id", "service_id", "program_service_id", *BOOKING_RESOURCE_KEYS):
            validated_data.pop(key, None)
        notes = validated_data.pop("notes", None)
        if notes is None:
            notes = instance.notes
        buffer_before = assignment.buffer_before
        buffer_after = assignment.buffer_after
        exclusive_start, exclusive_end = compute_exclusive_bounds(
            validated_data["start"],
            validated_data["end"],
            buffer_before,
            buffer_after,
        )
        previous_start_datetime = instance.start_datetime
        with transaction.atomic():
            AppointmentHistory.objects.create(
                appointment=instance,
                previous_start_datetime=instance.start_datetime,
                previous_end_datetime=instance.end_datetime,
                previous_exclusive_start_datetime=instance.exclusive_start_datetime,
                previous_exclusive_end_datetime=instance.exclusive_end_datetime,
                actor=actor,
            )
            instance.start_datetime = validated_data["start"]
            instance.end_datetime = validated_data["end"]
            instance.duration_minutes = assignment.duration
            instance.buffer_before_minutes = buffer_before
            instance.buffer_after_minutes = buffer_after
            instance.exclusive_start_datetime = exclusive_start
            instance.exclusive_end_datetime = exclusive_end
            instance.modality = validated_data["modality"]
            instance.room = room
            instance.equipment = equipment
            instance.care_team = care_team
            instance.notes = notes
            instance.status = AppointmentStatus.CONFIRMED
            instance.is_late = False
            instance.late_by = None
            instance.save()
            instance.associate_links.all().delete()
            create_appointment_associates(
                instance,
                associates_payload,
                exclusive_start,
                exclusive_end,
            )
            sync_associate_status_snapshots(instance)
            create_audit_log(
                instance,
                actor,
                AppointmentAuditAction.RESCHEDULE,
            )
            schedule_queue_appointment_rescheduled(
                instance,
                previous_start_datetime=previous_start_datetime,
            )
        resolve_exceptions_for_appointment(
            instance,
            ExceptionResolution.RESCHEDULED,
        )
        detect_exceptions_for_appointment(instance)
        return instance


class AppointmentLifecycleSerializer(BaseSerializer):
    def validate(self, attrs):
        appointment = self.context["appointment"]
        action = self.context["action"]
        validate_transition(appointment.status, action)
        if action == "complete" and appointment.program_service is not None:
            ensure_program_covers_appointment_date(
                appointment.program_service.program,
                center_local_date(appointment.center, appointment.start_datetime),
                field_name="program_service_id",
            )
        return attrs

    def update(self, instance, validated_data):
        actor = validated_data.pop("actor")
        action = self.context["action"]
        with transaction.atomic():
            apply_status_change(instance, action)
            instance.refresh_from_db()
            if action == "complete":
                complete_appointment_redemption(instance, actor)
            elif action == "no-show":
                cancel_appointment_redemption(instance, actor)
                schedule_queue_appointment_no_show(instance)
            create_audit_log(instance, actor, LIFECYCLE_AUDIT_MAP[action])
        return instance
