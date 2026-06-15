from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer
from programs.models import TherapyProgramService, Program
from programs.services.models import Service, CenterServiceAssignment
from programs.services.serializers import (
    BaseServiceSerializer,
    BaseServiceSerializerMeta,
)
from programs.services.utils.constants import ServiceCategory
from programs.services.utils.db import (
    update_service_center_count,
    redeem_program_service,
)
from programs.utils.db import cancel_program_service


class TherapyServiceSerializer(BaseServiceSerializerMeta, BaseModelSerializer):
    is_active = serializers.BooleanField(default=True, required=False)
    is_locked = serializers.BooleanField(default=False, read_only=True)
    service_category_code = serializers.CharField(
        source="service_category", read_only=True
    )
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "is_global",
            "add_centers",
            "remove_centers",
            "centers",
            "service_category",
            "service_category_code",
            "image",
            "centers_count",
            "created_at",
            "updated_at",
            "is_active",
            "is_locked",
            "created_by",
        ]
        read_only_fields = ["service_category"]

    def create(self, validated_data):
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        if not add_centers and not remove_centers:
            raise serializers.ValidationError("Center IDs must be provided")
        validated_data["service_category"] = ServiceCategory.THERAPY
        with transaction.atomic():
            service = super().create(validated_data)
            self.add_centers_action(service, add_centers)
            self.remove_centers_action(service, remove_centers)
            update_service_center_count(service.pk)
        return service

    def update(self, instance: Service, validated_data):
        raise serializers.ValidationError("Update not allowed")


class TherapyServiceDetailSerializer(BaseServiceSerializerMeta, BaseModelSerializer):
    is_active = serializers.BooleanField(default=True, required=False)
    is_locked = serializers.BooleanField(default=False, read_only=True)
    service_category_code = serializers.CharField(
        source="service_category", read_only=True
    )
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "is_global",
            "add_centers",
            "remove_centers",
            "centers",
            "service_category",
            "service_category_code",
            "image",
            "centers_count",
            "created_at",
            "updated_at",
            "is_active",
            "is_locked",
            "created_by",
        ]
        read_only_fields = ["service_category"]

    def create(self, validated_data):
        raise serializers.ValidationError("Create not allowed")

    def update(self, instance: Service, validated_data):
        validated_data.pop("service_category", None)
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            self.add_centers_action(instance, add_centers)
            self.remove_centers_action(instance, remove_centers)
            if add_centers or remove_centers:
                update_service_center_count(instance.pk)
        return instance


class TherapyServiceRedeemSerializer(BaseModelSerializer):
    SINGLE = "single"
    ALL = "all"

    id = serializers.UUIDField(source="pk", read_only=True)
    service = BaseServiceSerializer(source="program_service.service", read_only=True)
    redemption_type = serializers.ChoiceField(
        choices=[(SINGLE, "Single"), (ALL, "All")],
        default=SINGLE,
        write_only=True,
    )
    center_id = serializers.UUIDField(write_only=True)
    redeemed_date = serializers.DateField(required=False, default=timezone.localdate())

    class Meta:
        model = TherapyProgramService
        fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "created_at",
            "redemption_type",
            "center_id",
            "redeemed_date",
        ]
        read_only_fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "created_at",
        ]

    def create(self, validated_data):
        therapy_program_service: TherapyProgramService = validated_data.pop(
            "therapy_program_service"
        )
        program_service = therapy_program_service.program_service
        redeemed_by = validated_data.pop("redeemed_by")
        redemption_type = validated_data["redemption_type"]
        center_id = validated_data["center_id"]
        redeemed_date = validated_data["redeemed_date"]
        if not program_service.is_active:
            raise serializers.ValidationError(
                "This service has been cancelled and cannot be redeemed."
            )

        program_is_valid = (
            Program.objects.filter(pk=program_service.program.pk)
            .exclude(expires_at__lt=timezone.localdate())
            .exists()
        )
        if not program_is_valid:
            raise serializers.ValidationError(
                "The program has expired, cannot redeem any services."
            )

        center = Center.objects.filter(pk=center_id).first()
        if not center:
            raise serializers.ValidationError({"center_id": "Invalid center ID."})

        service_is_available = CenterServiceAssignment.objects.filter(
            service=program_service.service, center_id=center_id, is_active=True
        ).exists()
        if not service_is_available:
            raise serializers.ValidationError(
                "This service is not available at the given center."
            )

        remaining = (
            therapy_program_service.sessions_count
            - therapy_program_service.sessions_used
        )
        if remaining <= 0:
            raise serializers.ValidationError("No sessions remaining for this service.")

        quantity_map = {self.SINGLE: 1, self.ALL: remaining}
        redeem_program_service(
            program_service.pk,
            center_id,
            redeemed_by,
            quantity_map[redemption_type],
            redeemed_date,
        )

        therapy_program_service.refresh_from_db(fields=["sessions_used"])
        return therapy_program_service


class TherapyProgramServiceCancelSerializer(BaseModelSerializer):
    cancellation_reason = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    cancelled_date = serializers.DateField(default=timezone.localdate(), required=False)
    cancelled_by = BaseUserSerializer(
        source="program_service.cancelled_by", read_only=True
    )

    class Meta:
        model = TherapyProgramService
        fields = ["cancellation_reason", "cancelled_by", "cancelled_date"]

    def create(self, validated_data):
        center = validated_data.get("center")
        therapy_program_service: TherapyProgramService = validated_data.pop(
            "therapy_program_service", None
        )
        cancelled_by = validated_data.pop("cancelled_by", None)
        cancellation_reason = validated_data.get("cancellation_reason")
        cancelled_date = validated_data.get("cancelled_date")
        if not therapy_program_service.program_service.is_active:
            raise serializers.ValidationError("Program service is already cancelled.")

        if (
            therapy_program_service.sessions_used
            >= therapy_program_service.sessions_count
        ):
            raise serializers.ValidationError(
                "Service cannot be cancelled since it is already used"
            )

        cancel_program_service(
            therapy_program_service.program_service.pk,
            therapy_program_service.program_service.program.pk,
            center_id=center.pk,
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
            cancelled_date=cancelled_date,
        )
        return therapy_program_service
