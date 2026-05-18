from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from services.models import Service, CenterServiceAssignment
from services.programs.models import Program, ProgramService
from services.programs.utils.db import cancel_program_service
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
    is_locked = serializers.BooleanField(default=False, read_only=True)

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
            "is_locked",
            "created_by",
        ]

    def get_centers(self, instance: Service):
        assignments = instance.center_assignments.select_related("center").filter(
            is_active=True
        )[:10]
        centers = [asg.center for asg in assignments]
        return BaseCenterSerializer(centers, many=True, context=self.context).data

    @classmethod
    def get_invalid_centers(cls, center_ids):
        _center_ids = set(
            Center.objects.filter(pk__in=center_ids).values_list("pk", flat=True)
        )
        return set(center_ids) - set(_center_ids)

    def add_centers_action(self, service: Service, add_centers: list) -> None:
        if not add_centers:
            return
        center_ids = [i.get("id") for i in add_centers]
        missing_ids = self.get_invalid_centers(center_ids)
        if missing_ids:
            raise serializers.ValidationError(
                {
                    "add_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
                }
            )

        assignments = [
            CenterServiceAssignment(service=service, center_id=cid, is_active=True)
            for cid in center_ids
        ]
        CenterServiceAssignment.objects.bulk_create(assignments, ignore_conflicts=True)

    def remove_centers_action(self, service: Service, remove_centers: list) -> None:
        if not remove_centers:
            return
        center_ids = [i.get("id") for i in remove_centers]
        missing_ids = self.get_invalid_centers(center_ids)
        if missing_ids:
            raise serializers.ValidationError(
                {
                    "remove_centers": f'Invalid center IDs provided: {", ".join(map(str, missing_ids))}'
                }
            )

        CenterServiceAssignment.objects.filter(
            service=service, center_id__in=center_ids
        ).delete()

    def create(self, validated_data):
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        if not add_centers and not remove_centers:
            raise serializers.ValidationError("Center IDs must be provided")
        with transaction.atomic():
            service = super().create(validated_data)
            self.add_centers_action(service, add_centers)
            self.remove_centers_action(service, remove_centers)
            update_service_center_count(service.pk)
            return service

    def update(self, instance: Service, validated_data):
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            self.add_centers_action(instance, add_centers)
            self.remove_centers_action(instance, remove_centers)
            if add_centers or remove_centers:
                update_service_center_count(instance.pk)
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
            "sessions_cancelled",
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

        if not CenterServiceAssignment.objects.filter(
                service=program_service.service, center_id=center_id, is_active=True
        ).exists():
            raise serializers.ValidationError(
                "This service is not available at the given center."
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
        center = validated_data.get('center')
        program_service: ProgramService = validated_data.pop("program_service", None)
        cancelled_by = validated_data.pop("cancelled_by", None)
        cancellation_reason = validated_data.get("cancellation_reason")
        if not program_service.is_active:
            raise serializers.ValidationError("Program service is already cancelled.")
        cancel_program_service(
            program_service.pk,
            program_service.program.pk,
            center_id=center.pk,
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
        )
        return program_service
