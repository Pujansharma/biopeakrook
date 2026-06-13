from django.db import transaction
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import MinimumCenterSerializer
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer
from programs.services.models import Service, CenterServiceAssignment
from programs.services.serializers import CenterIDSerializer
from programs.services.utils.constants import ServiceCategory
from programs.services.utils.db import update_service_center_count


class AssessmentServiceSerializer(BaseModelSerializer):
    add_centers = CenterIDSerializer(
        many=True, required=False, allow_null=True, allow_empty=True, write_only=True
    )
    remove_centers = CenterIDSerializer(
        many=True, required=False, allow_null=True, allow_empty=True, write_only=True
    )
    centers = serializers.SerializerMethodField(read_only=True)
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

    def get_centers(self, instance: Service):
        center_assignments = getattr(instance, "center_assignments")
        assignments = center_assignments.all()[:10]
        centers = [asg.center for asg in assignments]
        return MinimumCenterSerializer(centers, many=True, context=self.context).data

    @classmethod
    def remove_all_centers(cls, service):
        CenterServiceAssignment.objects.filter(service=service).delete()

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
        is_global = validated_data.pop("is_global", False)
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        if not add_centers and not remove_centers:
            raise serializers.ValidationError("Center IDs must be provided")
        validated_data["service_category"] = ServiceCategory.ASSESSMENT
        with transaction.atomic():
            service = super().create(validated_data)
            if is_global:
                self.remove_all_centers(service)
                add_centers = []
                remove_centers = []
            self.add_centers_action(service, add_centers)
            self.remove_centers_action(service, remove_centers)
            update_service_center_count(service.pk)
        return service

    def update(self, instance: Service, validated_data):
        is_global = validated_data.pop("is_global", instance.is_global)
        validated_data.pop("service_category", None)
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if is_global:
                self.remove_all_centers(service=instance)
                add_centers = []
                remove_centers = []
            self.add_centers_action(instance, add_centers)
            self.remove_centers_action(instance, remove_centers)
            if add_centers or remove_centers or is_global:
                update_service_center_count(instance.pk)
        return instance
