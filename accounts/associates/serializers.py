from django.db import transaction
from rest_framework import serializers

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.centers.models import Center
from accounts.users.models import User
from accounts.users.utils.constants import Gender
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer, BaseSerializer


class BaseAssociateSerializer(BaseModelSerializer):
    """Base associate serializer for display"""
    id = serializers.UUIDField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email', required=False)
    phone = PhoneNumberSerializerField(source='user.phone', required=False)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)
    gender = serializers.ChoiceField(
        source='user.gender', choices=Gender.CHOICES, required=False, allow_null=True
    )
    date_of_birth = serializers.DateField(source='user.date_of_birth', required=False)
    image = serializers.ImageField(source='user.image', required=False, allow_null=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', required=False, default=True)

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "specializations", "role", "is_admin", "is_external", "is_active",
            "date_joined", 'last_login', "updated_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if 'gender' in self.get_fields():
            rep['gender'] = instance.user.get_gender_display()
        return rep


class AssociateSerializer(BaseAssociateSerializer):
    """Serializers for admins to update or create associates"""

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "specializations", "role", "is_admin", "is_external", "is_active",
            "date_joined", 'last_login', "updated_at",
        ]

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        email = user_data.get('email')
        phone = user_data.get('phone')

        errors = {}
        if email and User.objects.filter(email__iexact=email).exists():
            errors['email'] = "User with this email already exists."
        if phone and User.objects.filter(phone__iexact=phone).exists():
            errors['phone'] = "User with this phone already exists."

        if errors:
            raise serializers.ValidationError(errors)

        with transaction.atomic():
            user = User.objects.create_user(**user_data)
            validated_data['user'] = user
            return super().create(validated_data)

    def update(self, instance: Associate, validated_data):
        user_data = validated_data.pop('user', {})
        is_active = user_data.get('is_active', False)
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save()
        validated_data['is_active'] = is_active
        return super().update(instance, validated_data)


class AssociateProfileSerializer(BaseAssociateSerializer):
    """Serializer only for associates to update or view their profile"""

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "specializations", "role", "is_admin", "is_external", "is_active",
            "date_joined", 'last_login', "updated_at",
        ]

    def create(self, validated_data):
        """Admins will create Associates"""

    def update(self, instance: Associate, validated_data):
        """Associates can update their profiles"""
        user_data = validated_data.pop('user', {})
        user_data.pop('email', None)
        user_data.pop('phone', None)

        validated_data.pop("is_admin", None)
        validated_data.pop("is_external", None)

        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save()
        return super().update(instance, validated_data)


class AssociateCenterLinkSerializer(BaseSerializer):
    """Serializer to link/delink associates to a center"""
    add = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True
    )
    remove = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True
    )

    @classmethod
    def retrieve_invalid_ids(cls, input_center_ids):
        existing_center_ids = set(
            Center.objects.filter(id__in=set(input_center_ids)).values_list('id', flat=True)
        )
        invalid_ids = set(input_center_ids) - existing_center_ids
        return invalid_ids

    def validate(self, attrs):
        add_center_ids = attrs.get('add', [])
        remove_center_ids = attrs.get('remove', [])

        if not add_center_ids and not remove_center_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        # Validate center UUIDs in 'add' exist
        if add_center_ids:
            invalid_ids = self.retrieve_invalid_ids(add_center_ids)
            if invalid_ids:
                raise serializers.ValidationError({
                    'add': f"Centers not found: {[str(uid) for uid in invalid_ids]}"
                })

        # Validate center UUIDs in 'remove' exist
        if remove_center_ids:
            invalid_ids = self.retrieve_invalid_ids(remove_center_ids)
            if invalid_ids:
                raise serializers.ValidationError({
                    'remove': f"Centers not found: {[str(uid) for uid in invalid_ids]}"
                })

        return attrs

    def create(self, validated_data):
        associate = validated_data.pop('associate', None)

        if not associate:
            raise serializers.ValidationError({
                'associate': 'Associate ID is missing or invalid'
            })

        add_center_ids = validated_data.get('add', [])
        remove_center_ids = validated_data.get('remove', [])

        # Remove centers (only those belonging to this associate)
        if remove_center_ids:
            AssociateCenterAssignment.objects.filter(
                center__pk__in=remove_center_ids,
                associate=associate
            ).delete()

        # Add new assignments via bulk_create
        if add_center_ids:
            # Get existing center assignments to avoid duplicates
            existing_center_ids = set(
                AssociateCenterAssignment.objects.filter(
                    associate=associate,
                    center_id__in=add_center_ids
                ).values_list('center_id', flat=True)
            )

            new_center_ids = set(add_center_ids) - existing_center_ids

            assignments = [
                AssociateCenterAssignment(
                    associate=associate,
                    center_id=center_id,
                )
                for center_id in new_center_ids
            ]

            AssociateCenterAssignment.objects.bulk_create(assignments)

        return associate
