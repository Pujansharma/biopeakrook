from django.db import transaction
from rest_framework import serializers

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateRole,
)
from accounts.associates.utils.db import create_associate_user_account
from accounts.centers.models import Center
from accounts.centers.serializers import CenterSerializer
from accounts.centers.utils.db import (
    increment_staff_count,
    increment_inactive_staff_count,
    decrement_inactive_staff_count,
)
from accounts.customers.models import (
    CustomerAssociateAssignment,
    CustomerCenterAssignment,
    CustomerProfile,
)
from accounts.serializers import BasePasswordCheckOptionalSerializer
from accounts.users.models import User
from accounts.users.serializers import BaseUserSerializer
from accounts.users.utils.constants import Gender
from accounts.utils.db import (
    check_admin_associate_user_exists,
    check_customer_user_exists,
)
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer, BaseSerializer


class BaseAssociateSerializer(BaseModelSerializer):
    """Base associate serializer for display"""

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
        model = Associate
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_external",
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


class AdminAssociateSerializer(
    BaseAssociateSerializer, BasePasswordCheckOptionalSerializer
):
    """Serializers for admins to update or create associates"""

    class Meta:
        model = Associate
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_external",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
            "password1",
            "password2",
        ]
        extra_kwargs = {"email": {"required": True}}

    def create(self, validated_data):
        """Admins will create via this serializer"""
        user_data = validated_data.pop("user", {})
        email = user_data.get("email")

        password = self.get_validated_password(validated_data)

        errors = check_admin_associate_user_exists(email)
        if errors:
            raise serializers.ValidationError(errors)

        with transaction.atomic():
            user = User.objects.create_user(**user_data, password=password, phone=None)
            validated_data["user"] = user
            associate = super().create(validated_data)
            create_associate_user_account(associate)
            return associate

    def update(self, instance: Associate, validated_data):
        """Only Admins will be able to update associates"""
        user_data = validated_data.pop("user", {})
        user_data.pop("phone", None)
        is_active = user_data.get("is_active", False)
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])
        validated_data["is_active"] = is_active
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        return rep


class AdminAssociateDetailSerializer(BaseAssociateSerializer):
    """Serializers for admins to update or create associates"""

    class Meta:
        model = Associate
        fields = [
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_external",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
        ]

    def create(self, validated_data):
        pass

    def update(self, instance: Associate, validated_data):
        """Only Admins will be able to update associates"""
        user_data = validated_data.pop("user", {})
        user_data.pop("phone", None)
        is_active = user_data.get("is_active", False)
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])
        validated_data["is_active"] = is_active
        return super().update(instance, validated_data)


class AssociateProfileSerializer(BaseAssociateSerializer):
    """Serializer only for associates to update or view their profile"""

    class Meta:
        model = Associate
        fields = [
            "id",
            "contact_phone",
            "email",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_external",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
        ]

    def create(self, validated_data):
        """Admins will create Associates"""

    def update(self, instance: Associate, validated_data):
        """Associates can update their profiles"""
        user_data = validated_data.pop("user", {})
        user_data.pop("email", None)
        user_data.pop("phone", None)

        validated_data.pop("is_admin", None)
        validated_data.pop("is_external", None)
        validated_data.pop("is_active", None)

        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])
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
            Center.objects.filter(id__in=set(input_center_ids)).values_list(
                "id", flat=True
            )
        )
        invalid_ids = set(input_center_ids) - existing_center_ids
        return invalid_ids

    def validate(self, attrs):
        add_centers = attrs.get("add", [])
        remove_centers = attrs.get("remove", [])

        add_center_ids = [c["id"] for c in add_centers]
        remove_center_ids = [c["id"] for c in remove_centers]

        if not add_center_ids and not remove_center_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        # Validate center UUIDs in 'add' exist
        if add_center_ids:
            invalid_ids = self.retrieve_invalid_ids(add_center_ids)
            if invalid_ids:
                raise serializers.ValidationError(
                    {"add": f"Centers not found: {[str(uid) for uid in invalid_ids]}"}
                )

        # Validate center UUIDs in 'remove' exist
        if remove_center_ids:
            invalid_ids = self.retrieve_invalid_ids(remove_center_ids)
            if invalid_ids:
                raise serializers.ValidationError(
                    {
                        "remove": f"Centers not found: {[str(uid) for uid in invalid_ids]}"
                    }
                )

        # Replace with flat UUID lists for downstream use
        attrs["add"] = add_centers
        attrs["remove"] = remove_center_ids

        return attrs

    def create(self, validated_data):
        associate = validated_data.pop("associate", None)

        if not associate:
            raise serializers.ValidationError(
                {"associate": "Associate ID is missing or invalid"}
            )

        add_centers = validated_data.get("add", [])
        remove_center_ids = validated_data.get("remove", [])

        # Remove centers (only those belonging to this associate)
        if remove_center_ids:
            AssociateCenterAssignment.objects.filter(
                center__pk__in=remove_center_ids, associate=associate
            ).delete()

        # Add or update assignments (upsert)
        if add_centers:
            assignments = [
                AssociateCenterAssignment(
                    associate=associate,
                    center_id=c["id"],
                    is_admin=c.get("is_admin", True),
                )
                for c in add_centers
            ]
            AssociateCenterAssignment.objects.bulk_create(
                assignments,
                update_conflicts=True,
                update_fields=["is_admin"],
                unique_fields=["associate", "center"],
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


class BaseAssociateRoleSerializer(BaseModelSerializer):
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = AssociateRole
        fields = [
            "id",
            "name",
            # "features",
            "role_tag",
            # "is_external",
            "is_system",
            "is_active",
            "created_at",
            "updated_at",
        ]


class AssociateRoleSerializer(BaseModelSerializer):
    is_active = serializers.BooleanField(default=True, required=False)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = AssociateRole
        fields = [
            "id",
            "name",
            "role_tag",
            "is_system",
            "created_by",
            "is_active",
            "created_at",
            "updated_at",
        ]


class BaseCenterAssociateSerializer(BaseModelSerializer):
    """Serializer to list Associates liked to a center"""

    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    email = serializers.EmailField(source="associate.user.email", read_only=True)
    phone = PhoneNumberSerializerField(source="associate.user.phone", read_only=True)
    first_name = serializers.CharField(
        source="associate.user.first_name", read_only=True
    )
    last_name = serializers.CharField(source="associate.user.last_name", read_only=True)
    gender = serializers.ChoiceField(
        source="associate.user.gender", choices=Gender.CHOICES, read_only=True
    )
    image = serializers.ImageField(source="associate.user.image", read_only=True)

    is_active = serializers.BooleanField(
        source="associate.user.is_active", read_only=True
    )
    is_admin = serializers.BooleanField(read_only=True)
    exists = serializers.BooleanField(read_only=True)

    # Nested objects
    role = BaseAssociateRoleSerializer(read_only=True)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "image",
            "is_active",
            "is_admin",
            "exists",
            "role",
            "created_by",
        ]


class CenterAssociateSerializer(
    BasePasswordCheckOptionalSerializer, BaseModelSerializer
):
    # Flatten user fields to root
    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    email = serializers.EmailField(
        source="associate.user.email", allow_null=True, required=True
    )
    contact_phone = PhoneNumberSerializerField(
        source="associate.contact_phone", allow_null=True, required=False
    )
    first_name = serializers.CharField(
        source="associate.user.first_name", required=True
    )
    last_name = serializers.CharField(
        source="associate.user.last_name", required=False, allow_null=True
    )
    gender = serializers.ChoiceField(
        source="associate.user.gender",
        choices=Gender.CHOICES,
        required=False,
        allow_null=True,
    )
    image = serializers.ImageField(
        source="associate.user.image", required=False, allow_null=True
    )

    is_active = serializers.BooleanField(
        source="associate.user.is_active", read_only=True
    )
    # Keep role as nested object
    role = BaseAssociateRoleSerializer(read_only=True)
    role_id = serializers.UUIDField(required=False, write_only=True)

    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            # User fields (flattened)
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "image",
            # Associate fields (flattened)
            "is_admin",
            "is_primary",
            "is_active",
            # Write only fields
            "role_id",
            "password1",
            "password2",
            "created_at",
            "updated_at",
            "role",
            "created_by",
        ]

    def create(self, validated_data):
        """Allows center admins or Associates with FULL feature to add associates"""
        center = validated_data.pop("center", None)
        if not center:
            raise serializers.ValidationError("Invalid Center ID provided.")

        associate_data = validated_data.pop("associate", {})
        user_data = associate_data.pop("user", {})
        role_id = validated_data.pop("role_id", None)

        is_admin = validated_data.pop("is_admin", False)

        email = user_data.get("email")
        contact_phone = associate_data.get("contact_phone")
        password1 = None
        role = None

        errors = {}
        if email and User.objects.filter(email__iexact=email).exists():
            errors["email"] = "User with this email already exists."
        if errors:
            raise serializers.ValidationError(errors)

        if is_admin and role_id:
            raise serializers.ValidationError(
                {"role_id": "System users cannot have associate roles"}
            )

        if not is_admin and role_id:
            role = AssociateRole.objects.filter(pk=role_id, center=center).first()
            if not role:
                raise serializers.ValidationError(
                    {"role_id": "Invalid role for this center."}
                )

        if is_admin:
            password1 = self.get_validated_password(validated_data)

        validated_data["is_admin"] = is_admin

        with transaction.atomic():
            user = User.objects.create_user(**user_data, password=password1, phone=None)
            associate = Associate.objects.create(
                user=user, contact_phone=contact_phone, **associate_data
            )
            create_associate_user_account(associate)

            assignment = AssociateCenterAssignment.objects.create(
                associate=associate,
                center=center,
                role=role,
                **validated_data,
            )

            if not assignment.is_primary:
                increment_staff_count(assignment.center.pk)

        return assignment

    def update(self, instance: AssociateCenterAssignment, validated_data):
        """Update not allowed in this serializer"""
        pass

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep


class CenterAssociateDetailSerializer(BaseModelSerializer):
    # Flatten user fields to root
    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    email = serializers.EmailField(
        source="associate.user.email", allow_null=True, required=True
    )
    contact_phone = PhoneNumberSerializerField(
        source="associate.contact_phone", allow_null=True, required=False
    )
    first_name = serializers.CharField(
        source="associate.user.first_name", required=True
    )
    last_name = serializers.CharField(
        source="associate.user.last_name", required=False, allow_null=True
    )
    gender = serializers.ChoiceField(
        source="associate.user.gender",
        choices=Gender.CHOICES,
        required=False,
        allow_null=True,
    )
    image = serializers.ImageField(
        source="associate.user.image", required=False, allow_null=True
    )

    # Keep role as nested object
    role = AssociateRoleSerializer(read_only=True)
    role_id = serializers.UUIDField(required=True, write_only=True)

    # Assignment fields already at root
    # is_admin, mode, is_primary come from the model directly

    is_active = serializers.BooleanField(
        source="associate.user.is_active", read_only=True
    )

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            # User fields (flattened)
            "id",
            "email",
            "contact_phone",
            "first_name",
            "last_name",
            "gender",
            "image",
            # Associate fields (flattened)
            # Role (nested)
            "role",
            "role_id",
            # Assignment fields (native)
            "is_admin",
            "mode",
            "is_primary",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def update(self, instance: AssociateCenterAssignment, validated_data):
        """Update user fields, associate fields, and role on the assignment."""
        associate_data = validated_data.pop("associate", {})
        user_data = associate_data.pop("user", {})
        user_data.pop("phone", None)
        role_id = validated_data.pop("role_id", None)

        user = instance.associate.user

        email = user_data.get("email")

        errors = {}
        if (
            email
            and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
        ):
            errors["email"] = "User with this email already exists."

        if errors:
            raise serializers.ValidationError(errors)

        if role_id:
            if instance.is_admin:
                raise serializers.ValidationError(
                    {"role_id": "Roles cannot be assigned to admin associates."}
                )
            if not AssociateRole.objects.filter(
                pk=role_id, center=instance.center
            ).exists():
                raise serializers.ValidationError(
                    {"role_id": "Invalid role for this center."}
                )

        was_active = user.is_active

        if user_data:
            for key, value in user_data.items():
                setattr(user, key, value)
            user.save(update_fields=[*user_data.keys(), "updated_at"])

        if associate_data:
            associate = instance.associate
            for key, value in associate_data.items():
                setattr(associate, key, value)
            associate.save(update_fields=[*associate_data.keys(), "updated_at"])

        if instance.is_primary and "is_active" in user_data:
            is_now_active = user_data["is_active"]
            if not is_now_active and was_active:
                increment_inactive_staff_count(instance.center)
            if is_now_active and not was_active:
                decrement_inactive_staff_count(instance.center)

        return super().update(instance, validated_data)

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep


class AssociateCenterPermissionSerializer(BaseModelSerializer):
    role = AssociateRoleSerializer(read_only=True)

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            "role",
            "is_admin",
            "mode",
            "is_primary",
            "is_active",
            "created_at",
            "updated_at",
        ]


class AssociateLinkedProfileSerializer(BaseModelSerializer):
    """Serializer for listing customer profiles linked to an associate."""

    id = serializers.UUIDField(source="customer_profile.id", read_only=True)
    first_name = serializers.CharField(
        source="customer_profile.first_name", read_only=True
    )
    last_name = serializers.CharField(
        source="customer_profile.last_name", read_only=True
    )
    gender = serializers.CharField(source="customer_profile.gender", read_only=True)
    date_of_birth = serializers.DateField(
        source="customer_profile.date_of_birth", read_only=True
    )
    image = serializers.ImageField(source="customer_profile.image", read_only=True)
    contact_email = serializers.EmailField(
        source="customer_profile.customer.contact_email", read_only=True
    )
    phone = PhoneNumberSerializerField(
        source="customer_profile.customer.user.phone", read_only=True
    )
    is_main = serializers.BooleanField(
        source="customer_profile.is_main", read_only=True
    )
    is_active = serializers.BooleanField(
        source="customer_profile.customer.user.is_active", read_only=True
    )

    class Meta:
        model = CustomerAssociateAssignment
        fields = [
            "id",
            "contact_email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_main",
            "is_active",
            "created_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.customer_profile.get_gender_display()
        return rep


class AssociateAvailableProfileSerializer(BaseModelSerializer):
    """Serializer for listing customer profiles available to be linked to an associate."""

    contact_email = serializers.EmailField(
        source="customer.contact_email", read_only=True
    )
    phone = PhoneNumberSerializerField(source="customer.user.phone", read_only=True)
    is_active = serializers.BooleanField(
        source="customer.user.is_active", read_only=True
    )
    exists = serializers.BooleanField(read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "contact_email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_main",
            "is_active",
            "exists",
            "created_at",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.get_gender_display()
        return rep


class ProfileIDSerializer(BaseSerializer):
    id = serializers.UUIDField()


class AssociateProfileLinkSerializer(BaseSerializer):
    """Serializer to link/unlink customer profiles to an associate at a center."""

    center_id = serializers.UUIDField(write_only=True)
    add = ProfileIDSerializer(many=True, required=False, write_only=True)
    remove = ProfileIDSerializer(many=True, required=False, write_only=True)

    @classmethod
    def _invalid_profile_ids(cls, center_id, profile_ids: list) -> set:
        valid = set(
            CustomerCenterAssignment.objects.filter(
                center_id=center_id, customer_profile_id__in=profile_ids
            ).values_list("customer_profile_id", flat=True)
        )
        return set(profile_ids) - valid

    def validate(self, attrs):
        add_ids = [i["id"] for i in attrs.get("add", [])]
        remove_ids = [i["id"] for i in attrs.get("remove", [])]

        if not add_ids and not remove_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        center_id = attrs.get("center_id")
        if add_ids:
            invalid = self._invalid_profile_ids(center_id, add_ids)
            if invalid:
                raise serializers.ValidationError(
                    {
                        "add": f"Profiles not found at this center: {[str(uid) for uid in invalid]}"
                    }
                )
        if remove_ids:
            invalid = self._invalid_profile_ids(center_id, remove_ids)
            if invalid:
                raise serializers.ValidationError(
                    {
                        "remove": f"Profiles not found at this center: {[str(uid) for uid in invalid]}"
                    }
                )

        attrs["add"] = add_ids
        attrs["remove"] = remove_ids
        return attrs

    def create(self, validated_data):
        associate = validated_data.pop("associate")
        center_id = validated_data.pop("center_id")
        created_by = validated_data.pop("created_by", None)
        add_ids = validated_data.get("add", [])
        remove_ids = validated_data.get("remove", [])

        if add_ids:
            CustomerAssociateAssignment.objects.bulk_create(
                [
                    CustomerAssociateAssignment(
                        associate=associate,
                        customer_profile_id=profile_id,
                        center_id=center_id,
                        created_by=created_by,
                    )
                    for profile_id in add_ids
                ],
                update_conflicts=True,
                unique_fields=["customer_profile", "associate", "center"],
                update_fields=["created_by"],
            )

        if remove_ids:
            CustomerAssociateAssignment.objects.filter(
                associate=associate,
                center_id=center_id,
                customer_profile_id__in=remove_ids,
            ).delete()

        return associate
