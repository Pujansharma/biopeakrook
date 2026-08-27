from django.db import transaction
from rest_framework import serializers

from accounts.centers.models import Center, CenterOperatingHour
from accounts.centers.utils.db import generate_center_code
from accounts.organizations.utils.db import (
    increment_organization_centers_count,
    decrement_organization_centers_count,
    increment_organization_inactive_centers_count,
    decrement_organization_inactive_centers_count,
)
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer


class MinimumCenterSerializer(BaseModelSerializer):
    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
        ]


class BaseCenterSerializer(BaseModelSerializer):
    code = serializers.CharField(read_only=True)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            "address",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "pincode",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ServiceAvailableCenterSerializer(BaseCenterSerializer):
    exists = serializers.BooleanField(default=False)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            "address",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "pincode",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "is_active",
            "created_at",
            "updated_at",
            "exists",
        ]


class CenterSerializer(BaseCenterSerializer):
    """Serializer for Admins to create and update centers"""

    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            "address",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "state",
            "pincode",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
        ]

    @transaction.atomic
    def create(self, validated_data):
        """Method to create a center along with custom code"""
        code = generate_center_code()
        validated_data.update({"code": code})
        center = super().create(validated_data)
        increment_organization_centers_count()
        return center


class CenterDetailSerializer(BaseCenterSerializer):
    """Serializer for center details"""

    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            "address",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "pincode",
            "country",
            "phone",
            "email",
            "contact_person",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
        ]

    def update(self, instance: Center, validated_data):
        """Method to update a center"""
        validated_data.pop("code", None)
        validated_data.pop("created_by", None)

        is_active = validated_data.get("is_active")
        if is_active != instance.is_active and not is_active:
            decrement_organization_centers_count()
            increment_organization_inactive_centers_count()
        if is_active != instance.is_active and is_active:
            increment_organization_centers_count()
            decrement_organization_inactive_centers_count()

        return super().update(instance, validated_data)


class CenterWorkingHourSerializer(BaseModelSerializer):
    is_open = serializers.BooleanField(default=False, required=False)

    class Meta:
        model = CenterOperatingHour
        fields = [
            "id",
            "day_of_week",
            "is_open",
            "open_time",
            "close_time",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        """Creates an operating hour and validates time overlapping"""
        center = validated_data.get("center")
        day_of_week = validated_data.get("day_of_week")
        is_open = validated_data.get("is_open")

        if not is_open:
            exists = CenterOperatingHour.objects.filter(
                center=center, is_open=is_open, day_of_week=day_of_week
            ).exists()
            if exists:
                raise serializers.ValidationError(
                    "Center closed status already exists for this day of week"
                )

        return super().create(validated_data)


class AssociateAvailableCenterSerializer(BaseModelSerializer):
    exists = serializers.BooleanField(default=False, read_only=True)
    is_admin = serializers.BooleanField(default=False, read_only=True)
    is_care_staff = serializers.BooleanField(default=False, read_only=True)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            "exists",
            "is_active",
            "is_admin",
            "is_care_staff",
            "address",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "pincode",
        ]


class CustomerAvailableCenterSerializer(BaseModelSerializer):
    exists = serializers.BooleanField(default=False, read_only=True)
    is_primary = serializers.BooleanField(default=False, read_only=True)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            "exists",
            "is_active",
            "is_primary",
        ]
