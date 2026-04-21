from rest_framework import serializers

from accounts.admins.models import Admin
from accounts.admins.utils.db import create_admin_user
from accounts.users.utils.constants import Gender
from accounts.utils import get_user_model
from accounts.utils.db import check_user_exists
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer

User = get_user_model()


class BaseAdminUserSerializer(BaseModelSerializer):
    """Base admin user serializer for display"""
    id = serializers.UUIDField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email', required=False)
    phone = PhoneNumberSerializerField(source='user.phone', required=False, allow_null=True)
    first_name = serializers.CharField(source='user.first_name', required=False, allow_null=True)
    last_name = serializers.CharField(source='user.last_name', required=False, allow_null=True)
    gender = serializers.ChoiceField(
        source='user.gender', choices=Gender.CHOICES, required=False, allow_null=True
    )
    date_of_birth = serializers.DateField(
        source='user.date_of_birth', required=False, allow_null=True
    )
    image = serializers.ImageField(source='user.image', required=False, allow_null=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', required=False, default=True)

    class Meta:
        model = Admin
        fields = [
            'id', 'email', 'phone',
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            'is_active',
            'date_joined', 'last_login', 'updated_at',
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if 'gender' in self.get_fields():
            rep['gender'] = instance.user.get_gender_display()
        return rep


class AdminUserSerializer(BaseAdminUserSerializer):
    """Serializer for admins to create or update other admin users"""

    class Meta:
        model = Admin
        fields = [
            'id', 'email', 'phone',
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            'is_active',
            'date_joined', 'last_login', 'updated_at',
        ]
        extra_kwargs = {
            'email': {'required': True}
        }

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        email = user_data.get('email')
        phone = user_data.get('phone')

        errors = check_user_exists(email, phone)
        if errors:
            raise serializers.ValidationError(errors)

        if Admin.objects.filter(user__email__iexact=email).exists():
            raise serializers.ValidationError({'email': 'An admin with this email already exists.'})

        return create_admin_user(**user_data)

    def update(self, instance: Admin, validated_data):
        user_data = validated_data.pop('user', {})

        email = user_data.get('email')
        phone = user_data.get('phone')

        errors = {}
        if email and User.objects.filter(
                email__iexact=email
        ).exclude(pk=instance.user.pk).exists():
            errors['email'] = 'User with this email already exists.'
        if phone and User.objects.filter(
                phone__iexact=phone
        ).exclude(pk=instance.user.pk).exists():
            errors['phone'] = 'User with this phone already exists.'
        if errors:
            raise serializers.ValidationError(errors)

        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])

        return super().update(instance, validated_data)
