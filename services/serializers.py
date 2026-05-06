from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from services.models import Service
from services.programs.models import Program, ProgramService
from services.utils.db import redeem_program_service, update_service_center_count


class CenterIDSerializer(BaseSerializer):
    id = serializers.UUIDField(required=True, write_only=True)


class BaseServiceSerializer(BaseModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name"]


class ServiceSerializer(BaseModelSerializer):
    add_centers = CenterIDSerializer(
        many=True, required=False, allow_null=True, allow_empty=True, write_only=True
    )
    remove_centers = CenterIDSerializer(
        many=True, required=False, allow_null=True, allow_empty=True, write_only=True
    )
    centers = serializers.SerializerMethodField(read_only=True)
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "add_centers",
            "remove_centers",
            "centers",
            "centers_count",
            "created_at",
            "updated_at",
            "is_active",
            "created_by",
        ]

    def get_centers(self, instance: Service):
        qs = instance.centers.all()[:3]
        return BaseCenterSerializer(qs, many=True, context=self.context).data

    @classmethod
    def get_invalid_centers(cls, center_ids):
        _center_ids = set(
            Center.objects.filter(pk__in=center_ids).values_list("pk", flat=True)
        )
        return set(center_ids) - set(_center_ids)

    def create(self, validated_data):
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        _add_center_ids = [i.get("id") for i in add_centers]
        _remove_center_ids = [i.get("id") for i in remove_centers]

        if not add_centers and not remove_centers:
            raise serializers.ValidationError("Center IDs must be provided")

        if add_centers:
            missing_ids = self.get_invalid_centers(_add_center_ids)
            if missing_ids:
                raise serializers.ValidationError(
                    {
                        "add_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
                    }
                )
        if remove_centers:
            missing_ids = self.get_invalid_centers(_remove_center_ids)
            if missing_ids:
                raise serializers.ValidationError(
                    {
                        "remove_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
                    }
                )
        with transaction.atomic():
            service = super().create(validated_data)
            if add_centers:
                service.centers.add(*_add_center_ids)
            if remove_centers:
                service.centers.remvoe(*_remove_center_ids)
            update_service_center_count(service.pk)
            return service

    def update(self, instance, validated_data):
        validated_data.pop("add_centers", None)
        validated_data.pop("remove_centers", None)

        return instance


class ServiceRedeemSerializer(BaseModelSerializer):
    SINGLE = "single"
    ALL = "all"

    service = BaseServiceSerializer(read_only=True)
    redemption_type = serializers.ChoiceField(
        choices=[(SINGLE, "Single"), (ALL, "All")],
        default=SINGLE,
        write_only=True,
    )
    center_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "created_at",
            "redemption_type",
            "center_id",
        ]
        read_only_fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "created_at",
        ]

    def create(self, validated_data):
        program_service: ProgramService = validated_data.pop("program_service")
        redeemed_by = validated_data.pop("redeemed_by")
        redemption_type = validated_data["redemption_type"]
        center_id = validated_data["center_id"]

        if not program_service.is_active:
            raise serializers.ValidationError(
                "This service has been cancelled and cannot be redeemed."
            )

        if (
                not Program.objects.filter(pk=program_service.program.pk)
                        .exclude(expires_at__lt=timezone.localdate())
                        .exists()
        ):
            raise serializers.ValidationError(
                "The program has expired, cannot redeem any services."
            )

        center = Center.objects.filter(pk=center_id).first()
        if not center:
            raise serializers.ValidationError({"center_id": "Invalid center ID."})

        if not ProgramService.objects.filter(
                pk=program_service.pk, program__redeemable_centers=center_id
        ).exists():
            raise serializers.ValidationError(
                {"center_id": "Center is not in the program's redeemable centers."}
            )

        remaining = program_service.sessions_count - program_service.sessions_used
        if remaining <= 0:
            raise serializers.ValidationError("No sessions remaining for this service.")

        quantity_map = {self.SINGLE: 1, self.ALL: remaining}
        redeem_program_service(
            program_service.pk, center_id, redeemed_by, quantity_map[redemption_type]
        )

        program_service.refresh_from_db(fields=["sessions_used"])
        return program_service


class ProgramServiceCancelSerializer(BaseModelSerializer):
    cancellation_reason = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    class Meta:
        model = ProgramService
        fields = ["cancellation_reason", "cancelled_by"]

    def create(self, validated_data):
        program_service: ProgramService = validated_data.pop("program_service", None)
        cancelled_by = validated_data.pop("cancelled_by", None)
        cancellation_reason = validated_data.get("cancellation_reason")
        if not program_service.is_active:
            raise serializers.ValidationError("Program service is already cancelled.")
        program_service.is_active = False
        program_service.cancelled_by = cancelled_by
        program_service.program.cancelled_at = timezone.localtime()
        program_service.cancellation_reason = cancellation_reason
        program_service.save(
            update_fields=[
                "is_active",
                "cancelled_by",
                "cancelled_at",
                "cancellation_reason",
            ]
        )
        return program_service
