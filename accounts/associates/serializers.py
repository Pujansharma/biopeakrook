from rest_framework import serializers

from accounts.associates.models import Associate
from accounts.users.utils.constants import Gender
from core.utils.serializers import BaseModelSerializer


class BaseAssociateSerializer(BaseModelSerializer):
    """Base associate serializer for display"""
    id = serializers.UUIDField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email')
    phone = serializers.CharField(source='user.phone')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    gender = serializers.ChoiceField(source='user.gender', choices=Gender.CHOICES)
    date_of_birth = serializers.DateField(source='user.date_of_birth')
    image = serializers.ImageField(source='user.image')
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "specializations", "role", "is_admin", "is_external",
            "date_joined", 'last_login', "updated_at",
        ]


class AssociateSerializer(BaseAssociateSerializer):
    """Serializers for admins to update or create associates"""

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "specializations", "role", "is_admin", "is_external",
            "date_joined", 'last_login', "updated_at",
        ]

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class AssociateProfileSerializer(BaseAssociateSerializer):
    """Serializer only for associates to update or view their profile"""

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "specializations", "role", "is_admin", "is_external",
            "date_joined", 'last_login', "updated_at",
        ]

    def create(self, validated_data):
        """Admins will create Associates"""

    def update(self, instance, validated_data):
        """Associates can update their profiles"""
