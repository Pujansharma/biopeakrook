from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.associates.models import Associate, AssociateRole
from accounts.customers.models import CustomerProfile
from appointments.models import (
    Appointment,
    AppointmentAssociate,
    AppointmentAuditLog,
    AppointmentHistory,
    AppointmentIdempotencyKey,
)
from appointments.utils.codes import generate_appointment_code
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
    booking_has_complete_pin,
    compute_exclusive_bounds,
    get_center_service_assignment,
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
    schedule_queue_appointment_rescheduled,
)
from programs.services.models import Service

IDEMPOTENCY_TTL_HOURS = 24

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


class AppointmentPreferredSerializer(BaseSerializer):
    doctor_id = serializers.UUIDField(required=False)
    health_coach_id = serializers.UUIDField(required=False)
    room_id = serializers.UUIDField(required=False)
    care_team_id = serializers.UUIDField(required=False)


class AppointmentSlotFindSerializer(BaseSerializer):
    customer_profile_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    modality = serializers.ChoiceField(choices=AppointmentModes.choices)
    date = serializers.DateField()
    preferred = AppointmentPreferredSerializer(required=False)

    def validate_modality(self, value):
        if value == AppointmentModes.BOTH:
            raise serializers.ValidationError(
                "Modality must be virtual or in_person."
            )
        return value

    def validate(self, attrs):
        center = self.context["center"]
        customer_profile = resolve_center_customer_profile(
            center, attrs["customer_profile_id"]
        )
        service = resolve_center_service(center, attrs["service_id"])
        attrs["customer_profile"] = customer_profile
        attrs["service"] = service
        attrs["center"] = center
        attrs["preferred"] = normalize_preferred(attrs.get("preferred"))
        return attrs


class AppointmentAssociateInputSerializer(BaseSerializer):
    role_id = serializers.UUIDField()
    associate_id = serializers.UUIDField()


class AppointmentSlotSerializer(BaseSerializer):
    start = serializers.CharField()
    end = serializers.CharField()
    associates = AppointmentAssociateInputSerializer(many=True)
    room_id = serializers.UUIDField(allow_null=True)
    equipment_id = serializers.UUIDField(allow_null=True)


def normalize_preferred(preferred):
    preferred = preferred or {}
    normalized_preferred = {}
    for key, value in preferred.items():
        if value is not None:
            normalized_preferred[key] = str(value)
    if normalized_preferred.get("care_team_id") and (
        normalized_preferred.get("doctor_id")
        or normalized_preferred.get("health_coach_id")
    ):
        raise serializers.ValidationError(
            {
                "preferred": [
                    "care_team_id cannot be combined with doctor_id or health_coach_id."
                ]
            }
        )
    return normalized_preferred or None


class AppointmentBookSerializer(BaseSerializer):
    customer_profile_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    modality = serializers.ChoiceField(choices=AppointmentModes.choices)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    preferred = AppointmentPreferredSerializer(required=False)
    associates = AppointmentAssociateInputSerializer(many=True, required=False)
    room_id = serializers.UUIDField(required=False, allow_null=True)
    equipment_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_modality(self, value):
        if value == AppointmentModes.BOTH:
            raise serializers.ValidationError(
                "Modality must be virtual or in_person."
            )
        return value

    def validate(self, attrs):
        center = self.context["center"]
        customer_profile = resolve_center_customer_profile(
            center, attrs["customer_profile_id"]
        )
        service = resolve_center_service(center, attrs["service_id"])
        attrs["customer_profile"] = customer_profile
        attrs["service"] = service
        attrs["center"] = center
        attrs["associates"] = attrs.get("associates") or []
        attrs["preferred"] = normalize_preferred(attrs.get("preferred"))
        assignment = get_center_service_assignment(center, service)
        if assignment is None:
            raise serializers.ValidationError(
                "Service is not available at this center."
            )
        associates = attrs["associates"]
        room_id = attrs.get("room_id")
        modality = attrs["modality"]
        if (
            associates
            and modality == AppointmentModes.IN_PERSON
            and room_id is None
        ):
            raise serializers.ValidationError(
                "Pin requires room_id for in-person appointments."
            )
        has_pin = booking_has_complete_pin(modality, associates, room_id)
        has_preferred = bool(attrs["preferred"])
        has_role_requirements = any(
            requirement.is_active
            for requirement in assignment.role_requirements.all()
        )
        if has_role_requirements and not has_pin and not has_preferred:
            raise serializers.ValidationError(
                "Send preferred resources or a pinned associates list."
            )
        attrs["assignment"] = assignment
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
        validated_data.pop("preferred", None)
        validated_data.pop("associates", None)
        validated_data.pop("room_id", None)
        validated_data.pop("equipment_id", None)
        validated_data.pop("customer_profile_id", None)
        validated_data.pop("service_id", None)
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
    care_team = AppointmentCareTeamNestedSerializer(allow_null=True)
    associates = AppointmentAssociateNestedSerializer(
        source="associate_links", many=True
    )
    room = AppointmentRoomNestedSerializer(allow_null=True)
    equipment = AppointmentEquipmentNestedSerializer(allow_null=True)


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
    def validate(self, attrs):
        attrs = super().validate(attrs)
        appointment = self.context["appointment"]
        validate_transition(appointment.status, "reschedule")
        return attrs

    def update(self, instance, validated_data):
        assignment = validated_data.pop("assignment")
        room = validated_data.pop("room")
        equipment = validated_data.pop("equipment")
        associates_payload = validated_data.pop("associates_payload")
        care_team = validated_data.pop("care_team")
        actor = validated_data.pop("actor")
        validated_data.pop("preferred", None)
        validated_data.pop("associates", None)
        validated_data.pop("room_id", None)
        validated_data.pop("equipment_id", None)
        validated_data.pop("customer_profile_id", None)
        validated_data.pop("service_id", None)
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
        return attrs

    def update(self, instance, validated_data):
        actor = validated_data.pop("actor")
        action = self.context["action"]
        apply_status_change(instance, action)
        instance.refresh_from_db()
        create_audit_log(instance, actor, LIFECYCLE_AUDIT_MAP[action])
        return instance
