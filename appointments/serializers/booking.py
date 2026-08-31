from rest_framework import serializers

from accounts.customers.models import CustomerProfile
from appointments.utils.constants import AppointmentStatus
from appointments.utils.transitions import validate_transition
from core.utils.constants import AppointmentModes
from core.utils.serializers import BaseSerializer
from programs.services.models import Service


class AppointmentPreferredSerializer(BaseSerializer):
    doctor_id = serializers.UUIDField(required=False)
    health_coach_id = serializers.UUIDField(required=False)
    room_id = serializers.UUIDField(required=False)


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
        customer_profile = CustomerProfile.objects.filter(
            pk=attrs["customer_profile_id"],
            is_active=True,
        ).first()
        if customer_profile is None:
            raise serializers.ValidationError(
                {"customer_profile_id": ["Invalid or inactive customer profile."]}
            )
        service = Service.objects.filter(
            pk=attrs["service_id"],
            is_active=True,
        ).first()
        if service is None:
            raise serializers.ValidationError(
                {"service_id": ["Invalid or inactive service."]}
            )
        attrs["customer_profile"] = customer_profile
        attrs["service"] = service
        attrs["center"] = center
        preferred = attrs.get("preferred") or {}
        normalized_preferred = {}
        for key, value in preferred.items():
            if value is not None:
                normalized_preferred[key] = str(value)
        attrs["preferred"] = normalized_preferred or None
        return attrs


class AppointmentSlotSerializer(BaseSerializer):
    start = serializers.CharField()
    end = serializers.CharField()
    associates_by_role = serializers.DictField()
    rooms = serializers.ListField(required=False)
    equipment = serializers.ListField(required=False)


class AppointmentAssociateInputSerializer(BaseSerializer):
    role_id = serializers.UUIDField()
    associate_id = serializers.UUIDField()


class AppointmentBookSerializer(BaseSerializer):
    customer_profile_id = serializers.UUIDField()
    service_id = serializers.UUIDField()
    modality = serializers.ChoiceField(choices=AppointmentModes.choices)
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
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
        customer_profile = CustomerProfile.objects.filter(
            pk=attrs["customer_profile_id"],
            is_active=True,
        ).first()
        if customer_profile is None:
            raise serializers.ValidationError(
                {"customer_profile_id": ["Invalid or inactive customer profile."]}
            )
        service = Service.objects.filter(
            pk=attrs["service_id"],
            is_active=True,
        ).first()
        if service is None:
            raise serializers.ValidationError(
                {"service_id": ["Invalid or inactive service."]}
            )
        attrs["customer_profile"] = customer_profile
        attrs["service"] = service
        attrs["center"] = center
        attrs["associates"] = attrs.get("associates") or []
        return attrs


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


class AppointmentMarkLateSerializer(BaseSerializer):
    late_by = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        appointment = self.context["appointment"]
        validate_transition(appointment.status, "mark-late")
        return attrs


class AppointmentRescheduleSerializer(AppointmentBookSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        appointment = self.context["appointment"]
        validate_transition(appointment.status, "reschedule")
        return attrs


class AppointmentLifecycleSerializer(BaseSerializer):
    def validate(self, attrs):
        appointment = self.context["appointment"]
        action = self.context["action"]
        validate_transition(appointment.status, action)
        return attrs
