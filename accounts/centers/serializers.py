from django.db import transaction
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.utils.db import generate_center_code
from accounts.users.serializers import BaseUserSerializer
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer


class BaseCenterSerializer(BaseModelSerializer):
    code = serializers.CharField(read_only=True)
    phone = PhoneNumberSerializerField(required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Center
        fields = [
            "id",
            "code",
            "name",
            "address",
            "phone",
            "email",
            "contact_person",
            "modes",
            "status",
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
            "address",
            "phone",
            "email",
            "contact_person",
            "modes",
            "status",
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
            "address",
            "phone",
            "email",
            "contact_person",
            "modes",
            "status",
            "created_at",
            "updated_at",
            'created_by',
        ]

    def update(self, instance, validated_data):
        """Method to update a center"""
        validated_data.pop('code', None)
        validated_data.pop('created_by', None)
        return super().update(instance, validated_data)
