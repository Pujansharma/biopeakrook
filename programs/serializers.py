from rest_framework import serializers

from accounts.centers.serializers import MinimumCenterSerializer
from accounts.customers.serializers import BaseCustomerProfileSerializer
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from programs.models import Program, ProgramService, RedemptionHistory
from programs.services.serializers import BaseServiceSerializer


class BaseProgramSerializer(BaseModelSerializer):
    uid = serializers.CharField(read_only=True)
    profile = BaseCustomerProfileSerializer(source="customer_profile", read_only=True)
    sessions_count = serializers.IntegerField(
        source="therapy_program.sessions_count", read_only=True
    )
    sessions_used = serializers.IntegerField(
        source="therapy_program.sessions_used", read_only=True
    )

    class Meta:
        model = Program
        fields = [
            "id",
            "uid",
            "profile",
            "program_type",
            "notes",
            "expires_at",
            "is_complimentary",
            "price",
            "services_count",
            "sessions_count",
            "sessions_used",
            "redeemable_centers_count",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ProgramSerializer(BaseModelSerializer):
    uid = serializers.CharField(read_only=True)

    class Meta:
        model = Program
        fields = ["id", "uid"]


class BaseProgramServiceSerializer(BaseModelSerializer):
    service = BaseServiceSerializer(read_only=True)
    cancelled_by = BaseUserSerializer(read_only=True)
    can_redeem = serializers.BooleanField(default=True, read_only=True)
    sessions_count = serializers.IntegerField(
        source="therapy_service.sessions_count", read_only=True
    )
    sessions_used = serializers.IntegerField(
        source="therapy_service.sessions_used", read_only=True
    )
    sessions_cancelled = serializers.IntegerField(
        source="therapy_service.sessions_cancelled", read_only=True
    )
    redeem_code = serializers.CharField(
        source="therapy_service.redeem_code", read_only=True
    )

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "redeem_code",
            "created_at",
            "is_active",
            "can_redeem",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
        ]


class RedeemableCenterField(BaseSerializer):
    id = serializers.UUIDField(required=True)


class ServiceField(BaseSerializer):
    id = serializers.UUIDField(required=True)
    sessions_count = serializers.IntegerField(min_value=1, required=True)


class RedemptionHistoryAppointmentSerializer(BaseSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    start = serializers.DateTimeField(source="start_datetime", read_only=True)
    end = serializers.DateTimeField(source="end_datetime", read_only=True)


class ProgramServiceRedemptionHistorySerializer(BaseModelSerializer):
    redeem_center = MinimumCenterSerializer(read_only=True)
    redeemed_by = BaseUserSerializer(read_only=True)
    appointment = RedemptionHistoryAppointmentSerializer(read_only=True, allow_null=True)

    class Meta:
        model = RedemptionHistory
        fields = [
            "id",
            "redemption_type",
            "redeem_center",
            "redeemed_date",
            "redeemed_at",
            "quantity",
            "redeemed_by",
            "appointment",
        ]
        read_only_fields = fields
