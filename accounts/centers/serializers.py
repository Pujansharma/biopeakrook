from django.db import transaction
from rest_framework import serializers

from accounts.centers.models import Center, CenterOperatingHour
from accounts.centers.utils.db import generate_center_code
from accounts.users.serializers import BaseUserSerializer
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer


class BaseCenterSerializer(BaseModelSerializer):
    code = serializers.CharField(read_only=True)
    phone = PhoneNumberSerializerField(required=False, allow_null=True, allow_blank=True)
    status_code = serializers.CharField(source='status', read_only=True)

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
            "phone",
            "email",
            "contact_person",
            "modes",
            "status",
            "status_code",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "created_at",
            "updated_at"
        ]


class CenterSerializer(BaseCenterSerializer):
    """Serializer for Admins to create and update centers"""

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
            "phone",
            "email",
            "contact_person",
            "modes",
            "status",
            "status_code",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "created_at",
            "updated_at"
        ]

    @transaction.atomic
    def create(self, validated_data):
        """Method to create a center along with custom code"""
        code = generate_center_code()
        validated_data.update({
            'code': code
        })
        return super().create(validated_data)


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
            "modes",
            "status",
            "status_code",
            "staff_count",
            "inactive_staff_count",
            "customer_count",
            "inactive_customer_count",
            "created_at",
            "updated_at",
            'created_by',
        ]

    def update(self, instance, validated_data):
        """Method to update a center"""
        validated_data.pop('code', None)
        validated_data.pop('created_by', None)
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
        center = validated_data.get('center')
        day_of_week = validated_data.get('day_of_week')
        is_open = validated_data.get('is_open')

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

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "image",
            'exists',
            "is_active",
        ]
