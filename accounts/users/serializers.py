from rest_framework import serializers

from accounts.users.models import User
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer


class UserProfileSerializer(BaseModelSerializer):
    email = serializers.CharField(read_only=True, required=False)
    phone = PhoneNumberSerializerField(read_only=True, required=False)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "date_joined",
            "last_login",
            "updated_at",
        )
        read_only_fields = ["date_joined", "last_login"]


class BaseUserSerializer(BaseModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "image", "last_login"]
        read_only_fields = fields
