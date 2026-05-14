from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from accounts.admins.models import Admin
from accounts.admins.utils.db import create_admin_user
from accounts.organizations.utils.db import (
    increment_organization_admins_count,
    update_organization_staff_count,
)
from accounts.serializers import BasePasswordCheckSerializer
from accounts.users.serializers import BaseUserSerializer
from accounts.users.utils.constants import Gender
from accounts.utils import get_user_model
from accounts.utils.db import check_admin_associate_user_exists
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer

User = get_user_model()


class BaseAdminUserSerializer(BaseModelSerializer):
    """Base admin user serializer for display"""

    id = serializers.UUIDField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", required=False)
    contact_phone = PhoneNumberSerializerField(required=False, allow_null=True)
    first_name = serializers.CharField(
        source="user.first_name", required=False, allow_null=True
    )
    last_name = serializers.CharField(
        source="user.last_name", required=False, allow_null=True
    )
    gender = serializers.ChoiceField(
        source="user.gender", choices=Gender.CHOICES, required=False, allow_null=True
    )
    date_of_birth = serializers.DateField(
        source="user.date_of_birth", required=False, allow_null=True
    )
    image = serializers.ImageField(source="user.image", required=False, allow_null=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    is_active = serializers.BooleanField(
        source="user.is_active", required=False, default=True
    )

    class Meta:
        model = Admin
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.user.get_gender_display()
        return rep


class AdminUserSerializer(BaseAdminUserSerializer, BasePasswordCheckSerializer):
    """Serializer for admins to create or update other admin users"""

    class Meta:
        model = Admin
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_active",
            "password1",
            "password2",
            "date_joined",
            "last_login",
            "updated_at",
        ]
        extra_kwargs = {
            "email": {"required": True},
        }

    def create(self, validated_data):
        password = validated_data.get("password1")
        user_data = validated_data.pop("user", {})
        contact_phone = validated_data.get("contact_phone")
        email = user_data.get("email")

        errors = check_admin_associate_user_exists(email)
        if errors:
            raise serializers.ValidationError(errors)

        if Admin.objects.filter(user__email__iexact=email).exists():
            raise serializers.ValidationError(
                {"email": "An admin with this email already exists."}
            )

        admin = create_admin_user(
            **user_data,
            password=password,
            contact_phone=contact_phone,
        )
        increment_organization_admins_count()
        return admin

    def update(self, instance: Admin, validated_data):
        """Update not allowed in this serializer"""


class AdminUserDetailSerializer(BaseAdminUserSerializer):
    """Serializer for admins to update other admin users"""

    is_active = serializers.BooleanField(source="user.is_active", required=False)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Admin
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
            "created_by",
        ]
        extra_kwargs = {
            "email": {"required": True},
        }

    def create(self, validated_data):
        """Create not allowed in this serializer"""

    def update(self, instance: Admin, validated_data):
        request = self.context.get("request", None)
        user: User | None = getattr(request, "user", None)

        if not user:
            raise serializers.ValidationError("Invalid user provided")

        if user and user.pk == instance.user.id:
            raise PermissionDenied()

        validated_data.pop("password1", None)
        validated_data.pop("password2", None)

        user_data = validated_data.pop("user", {})
        user_data.pop("phone", None)
        is_active = user_data.get("is_active", user.is_active)
        validated_data["is_active"] = is_active

        email = user_data.get("email")

        errors = {}

        if (
            email
            and User.objects.filter(email__iexact=email)
            .exclude(pk=instance.user.pk)
            .exists()
        ):
            errors["email"] = "User with this email already exists."

        if errors:
            raise serializers.ValidationError(errors)

        was_active = instance.user.is_active

        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])

        if "is_active" in user_data and is_active != was_active:
            update_organization_staff_count()

        return super().update(instance, validated_data)


class AdminProfileSerializer(BaseAdminUserSerializer):
    """Serializer for admins to retrieve and update their own profile"""

    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Admin
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
        ]

    def create(self, validated_data):
        """Create not allowed in this serializer"""

    def update(self, instance: Admin, validated_data):
        user_data = validated_data.pop("user", {})
        user_data.pop("email", None)
        user_data.pop("phone", None)

        validated_data.pop("is_active", None)

        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])

        return super().update(instance, validated_data)
