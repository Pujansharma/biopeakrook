from django.db import transaction
from rest_framework import serializers

from accounts.associates.models import Associate, AssociateCenterAssignment, AssociateRole
from accounts.associates.utils.db import create_associate_user_account
from accounts.centers.models import Center
from accounts.centers.serializers import CenterSerializer
from accounts.users.models import User
from accounts.users.utils.constants import Gender
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer, BaseSerializer


class BaseAssociateSerializer(BaseModelSerializer):
    """Base associate serializer for display"""
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
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "is_external", "is_active",
            "date_joined", 'last_login', "updated_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if 'gender' in self.get_fields():
            rep['gender'] = instance.user.get_gender_display()
        return rep


class AdminAssociateSerializer(BaseAssociateSerializer):
    """Serializers for admins to update or create associates"""

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "is_external", "is_active",
            "date_joined", 'last_login', "updated_at",
        ]
        extra_kwargs = {
            'email': {
                'required': True
            }
        }

    def create(self, validated_data):
        """Admins will create via this serializer"""
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
            associate = super().create(validated_data)
            create_associate_user_account(associate)
            return associate

    def update(self, instance: Associate, validated_data):
        """Only Admins will be able to update associates"""
        user_data = validated_data.pop('user', {})
        is_active = user_data.get('is_active', False)
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save()
        validated_data['is_active'] = is_active
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return rep


class AssociateProfileSerializer(BaseAssociateSerializer):
    """Serializer only for associates to update or view their profile"""

    class Meta:
        model = Associate
        fields = [
            'id', "email", "phone",
            'first_name', 'last_name', 'gender', 'date_of_birth', 'image',
            "is_external", "is_active",
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


class CenterIDSerializer(BaseSerializer):
    id = serializers.UUIDField()
    is_admin = serializers.BooleanField(default=True, required=False)


class AdminAssociateCenterLinkSerializer(BaseSerializer):
    """Serializer to link/delink associates to a center by admin"""
    add = CenterIDSerializer(many=True, required=False, write_only=True)
    remove = CenterIDSerializer(many=True, required=False, write_only=True)

    @classmethod
    def retrieve_invalid_ids(cls, input_center_ids):
        existing_center_ids = set(
            Center.objects.filter(id__in=set(input_center_ids)).values_list('id', flat=True)
        )
        invalid_ids = set(input_center_ids) - existing_center_ids
        return invalid_ids

    def validate(self, attrs):
        add_centers = attrs.get('add', [])
        remove_centers = attrs.get('remove', [])

        add_center_ids = [c['id'] for c in add_centers]
        remove_center_ids = [c['id'] for c in remove_centers]

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

        # Replace with flat UUID lists for downstream use
        attrs['add'] = add_centers
        attrs['remove'] = remove_center_ids

        return attrs

    def create(self, validated_data):
        associate = validated_data.pop('associate', None)

        if not associate:
            raise serializers.ValidationError({
                'associate': 'Associate ID is missing or invalid'
            })

        add_centers = validated_data.get('add', [])
        remove_center_ids = validated_data.get('remove', [])

        # Remove centers (only those belonging to this associate)
        if remove_center_ids:
            AssociateCenterAssignment.objects.filter(
                center__pk__in=remove_center_ids,
                associate=associate
            ).delete()

        # Add or update assignments (upsert)
        if add_centers:
            assignments = [
                AssociateCenterAssignment(
                    associate=associate,
                    center_id=c['id'],
                    is_admin=c.get('is_admin', True),
                )
                for c in add_centers
            ]
            AssociateCenterAssignment.objects.bulk_create(
                assignments,
                update_conflicts=True,
                update_fields=['is_admin'],
                unique_fields=['associate', 'center'],
            )

        return associate


class AssociateCenterSerializer(CenterSerializer):
    is_admin = serializers.BooleanField(default=False, read_only=True)

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
            "created_at",
            "updated_at",
            "is_active",
            "is_admin",
        ]


class AssociateRoleSerializer(BaseModelSerializer):
    class Meta:
        model = AssociateRole
        fields = [
            'id',
            "name",
            "features",
            "role_tag",
            "is_external",
            "is_system",
            # "created_by",
            "is_active",
            "created_at",
            "updated_at"
        ]


class CenterAssociateListSerializer(BaseModelSerializer):
    # Flatten user fields to root
    id = serializers.UUIDField(source='associate.user.id', read_only=True)
    email = serializers.EmailField(source='associate.user.email', read_only=True)
    phone = serializers.CharField(source='associate.user.phone', read_only=True)
    first_name = serializers.CharField(source='associate.user.first_name', read_only=True)
    last_name = serializers.CharField(source='associate.user.last_name', read_only=True)
    image = serializers.ImageField(source='associate.user.image', read_only=True)

    # Flatten associate fields to root
    is_external = serializers.BooleanField(source='associate.is_external', read_only=True)

    # Keep role as nested object
    role = AssociateRoleSerializer(read_only=True)

    # Assignment fields already at root
    # is_admin, mode, is_primary come from the model directly

    is_active = serializers.BooleanField(source='associate.user.is_active', read_only=True)

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            # User fields (flattened)
            'id', 'email', 'phone', 'first_name', 'last_name', 'image',
            # Associate fields (flattened)
            'is_external',
            # Role (nested)
            'role',
            # Assignment fields (native)
            'is_admin', 'mode', 'is_primary',
            'is_active', 'created_at', 'updated_at',
        ]


class AssociateCenterPermissionSerializer(BaseModelSerializer):
    role = AssociateRoleSerializer(read_only=True)

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            'role',
            'is_admin', 'mode', 'is_primary',
            'is_active', 'created_at', 'updated_at',
        ]
