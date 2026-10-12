from typing import Any

from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.associates.models import (
    Associate,
    AssociateCenterAssignment,
    AssociateRole,
)

ASSOCIATE_ROLE_CENTER_NAME_UNIQUE = "uniq_associate_role_center_name"
ASSOCIATE_ROLE_NAME_CLASH = "A role with this name already exists at this center."


def is_associate_role_center_name_unique_violation(error: IntegrityError) -> bool:
    return ASSOCIATE_ROLE_CENTER_NAME_UNIQUE in str(error)
from accounts.associates.utils.constants import AssociateTitle
from accounts.associates.utils.db import (
    create_associate_user_account,
    replace_assignment_roles,
    update_associate_centers_count,
)
from accounts.associates.utils.roles import (
    assignment_active_roles,
    resolve_center_roles,
)
from accounts.utils.helper import dedupe_ids
from accounts.centers.models import Center
from accounts.centers.serializers import MinimumCenterSerializer
from accounts.centers.utils.db import (
    increment_staff_count,
    increment_inactive_staff_count,
    decrement_inactive_staff_count,
    refresh_staff_counts,
)
from accounts.customers.models import (
    CustomerAssociateAssignment,
    CustomerCenterAssignment,
    CustomerProfile,
)
from accounts.organizations.utils.db import (
    increment_organization_admins_count,
    update_organization_staff_count,
)
from accounts.serializers import BasePasswordCheckOptionalSerializer
from accounts.users.models import User
from accounts.users.serializers import BaseUserSerializer
from accounts.users.utils.constants import Gender
from accounts.utils.db import (
    check_admin_associate_user_exists,
)
from accounts.verifications.utils.helper import send_registration_code
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer, BaseSerializer




def assignment_roles_representation(assignment):
    if assignment is None:
        return {"role_ids": [], "roles": []}
    cached = getattr(assignment, "_assignment_roles_representation", None)
    if cached is not None:
        return cached
    roles = assignment_active_roles(assignment)
    payload = {
        "role_ids": [role.pk for role in roles],
        "roles": BaseAssociateRoleSerializer(roles, many=True).data,
    }
    assignment._assignment_roles_representation = payload
    return payload


class AssignmentRoleIdsField(serializers.ListField):
    def __init__(self, **kwargs):
        kwargs.setdefault("child", serializers.UUIDField())
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_empty", True)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        return instance

    def to_representation(self, instance):
        return assignment_roles_representation(instance)["role_ids"]


class AssociateValidationMixin:
    @classmethod
    def validate_experience(cls, value: float) -> float | None:
        if not value:
            return None
        if value <= 0:
            raise serializers.ValidationError("Experience must be greater than 0.")
        return value

    @classmethod
    def validate_qualifications(cls, value: list) -> list:
        if len(value) > 2:
            raise serializers.ValidationError("Maximum 2 qualifications allowed.")
        return value

    @classmethod
    def validate_professions(cls, value: list) -> list:
        if len(value) > 2:
            raise serializers.ValidationError("Maximum 2 professions allowed.")
        return value


class AssociateSourceMixinSerializer(AssociateValidationMixin, BaseSerializer):
    title = serializers.ChoiceField(
        source="associate.title",
        required=False,
        allow_null=True,
        allow_blank=True,
        choices=[*AssociateTitle.choices],
    )
    description = serializers.CharField(
        source="associate.description",
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    tagline = serializers.CharField(
        source="associate.tagline",
        max_length=100,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    experience = serializers.FloatField(
        source="associate.experience", required=False, allow_null=True
    )
    qualifications = serializers.ListField(
        source="associate.qualifications",
        required=False,
        max_length=2,
        child=serializers.CharField(max_length=50),
    )
    professions = serializers.ListField(
        source="associate.professions",
        required=False,
        max_length=2,
        child=serializers.CharField(max_length=50),
    )
    has_verified_badge = serializers.BooleanField(
        source="associate.has_verified_badge", required=False
    )

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        if "title" in self.get_fields():
            rep["title"] = instance.associate.get_title_display()
        return rep


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

    def validate_name(self, value):
        return value.strip()

    def validate(self, attrs):
        name = attrs.get("name")
        if name is None and self.instance is not None:
            name = self.instance.name
        if name:
            center = self.context.get("center")
            if center is None and self.instance is not None:
                center = self.instance.center
            if center is not None:
                clash = AssociateRole.objects.filter(center=center, name__iexact=name)
                if self.instance is not None:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise serializers.ValidationError(
                        {"name": [ASSOCIATE_ROLE_NAME_CLASH]}
                    )
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as error:
            if not is_associate_role_center_name_unique_violation(error):
                raise
            raise serializers.ValidationError(
                {"name": [ASSOCIATE_ROLE_NAME_CLASH]}
            ) from error

    def update(self, instance, validated_data):
        try:
            with transaction.atomic():
                return super().update(instance, validated_data)
        except IntegrityError as error:
            if not is_associate_role_center_name_unique_violation(error):
                raise
            raise serializers.ValidationError(
                {"name": [ASSOCIATE_ROLE_NAME_CLASH]}
            ) from error


class BaseAssociateSerializer(AssociateValidationMixin, BaseModelSerializer):
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
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    is_active = serializers.BooleanField(
        source="user.is_active", required=False, default=True
    )
    qualifications = serializers.ListField(
        required=False, max_length=2, child=serializers.CharField(max_length=50)
    )
    professions = serializers.ListField(
        required=False, max_length=2, child=serializers.CharField(max_length=50)
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
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.user.get_gender_display()
        return rep


class CenterIDSerializer(BaseSerializer):
    id = serializers.UUIDField(required=True, write_only=True)
    is_admin = serializers.BooleanField(default=False, required=False)
    is_care_staff = serializers.BooleanField(default=False, required=False)


class AdminAssociateSerializer(
    BaseAssociateSerializer, BasePasswordCheckOptionalSerializer
):
    """Serialize admin associate list and create operations with a center preview."""
    centers_count = serializers.IntegerField(default=0, read_only=True)
    centers = serializers.SerializerMethodField(read_only=True)

    add_centers = CenterIDSerializer(
        many=True, write_only=True, required=True, allow_empty=False
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
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
            "password1",
            "password2",
            "add_centers",
            "centers_count",
            "centers",
        ]
        extra_kwargs = {"email": {"required": True}}

    def get_centers(self, instance):
        center_assignments = getattr(instance, 'center_assignments', None)
        if not center_assignments:
            return None
        assignments = center_assignments.all()[:3]
        centers = [assignment.center for assignment in assignments]
        return MinimumCenterSerializer(centers, many=True, context=self.context).data

    @classmethod
    def retrieve_invalid_center_ids(cls, input_center_ids):
        existing_center_ids = set(
            Center.objects.filter(
                id__in=set(input_center_ids)
            ).values_list(
                "id", flat=True
            )
        )
        invalid_ids = set(input_center_ids) - existing_center_ids
        return invalid_ids

    def validate(self, attrs: Any) -> Any:
        add_centers_by_id = {
            center_data["id"]: center_data
            for center_data in attrs.get("add_centers", [])
        }
        add_centers = list(add_centers_by_id.values())
        add_center_ids = list(add_centers_by_id)

        invalid_ids = self.retrieve_invalid_center_ids(add_center_ids)
        if invalid_ids:
            raise serializers.ValidationError(
                {
                    "add_centers": (
                        f"Centers not found: "
                        f"{[str(center_id) for center_id in invalid_ids]}"
                    )
                }
            )

        invalid_flag_center_ids = [
            center_data["id"]
            for center_data in add_centers
            if not center_data["is_admin"] and not center_data["is_care_staff"]
        ]
        if invalid_flag_center_ids:
            raise serializers.ValidationError(
                {
                    "add_centers": (
                        "At least one of 'is_admin' or 'is_care_staff' must be "
                        f"true for centers: "
                        f"{[str(center_id) for center_id in invalid_flag_center_ids]}"
                    )
                }
            )

        attrs["add_centers"] = add_centers
        return attrs

    def create(self, validated_data):
        """Create an associate and its center assignments.

        The persisted centers count is updated with a single query. The returned
        instance is intentionally not refreshed because clients retrieve complete
        center information and its authoritative pagination count from
        GET /associates/<associate_id>/centers/.
        """
        add_centers = validated_data.pop("add_centers")
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
            # center_id is intentional and avoids unnecessary Django ORM hydration.
            assignments = [
                AssociateCenterAssignment(
                    associate=associate,
                    center_id=center_data["id"],
                    is_admin=center_data["is_admin"],
                    is_care_staff=center_data["is_care_staff"],
                    created_by=associate.created_by,
                )
                for center_data in add_centers
            ]
            AssociateCenterAssignment.objects.bulk_create(assignments)

            center_ids = [center_data["id"] for center_data in add_centers]
            refresh_staff_counts(center_ids)
            update_associate_centers_count(associate.pk)
            increment_organization_admins_count()
            return associate

    def update(self, instance: Associate, validated_data):
        """Only Admins will be able to update associates"""
        validated_data.pop('add_centers', None)
        user_data = validated_data.pop("user", {})
        user_data.pop("phone", None)
        is_active = user_data.get("is_active", False)
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        instance.user.save(update_fields=[*user_data.keys(), "updated_at"])
        validated_data["is_active"] = is_active
        with transaction.atomic():
            if is_active != instance.is_active:
                update_organization_staff_count()
            return super().update(instance, validated_data)


class AdminAssociateDetailSerializer(BaseAssociateSerializer):
    """Serialize admin associate detail data without center assignments.

    Complete center information and its authoritative pagination count are
    available from GET /associates/<associate_id>/centers/.
    """

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
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
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

        if is_active != instance.is_active:
            update_organization_staff_count()

        return super().update(instance, validated_data)


class CenterAssignmentAssociateProfileSerializer(
    AssociateSourceMixinSerializer, BaseModelSerializer
):
    """Serializer only for associates to update or view their profile"""

    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    is_active = serializers.BooleanField(
        source="associate.user.is_active", read_only=True
    )
    email = serializers.EmailField(source="associate.user.email", read_only=True)
    contact_phone = PhoneNumberSerializerField(
        source="associate.contact_phone", required=False
    )
    first_name = serializers.CharField(
        source="associate.user.first_name", required=False
    )
    last_name = serializers.CharField(source="associate.user.last_name", required=False)
    gender = serializers.ChoiceField(
        source="associate.user.gender", required=False, choices=Gender.CHOICES
    )
    date_of_birth = serializers.DateField(
        source="associate.user.date_of_birth", required=False
    )
    image = serializers.ImageField(source="associate.user.image", required=False)
    date_joined = serializers.DateField(
        source="associate.date_joined", required=False, allow_null=True
    )
    last_login = serializers.DateTimeField(
        source="associate.user.last_login", read_only=True
    )
    is_admin = serializers.BooleanField(read_only=True)
    is_care_staff = serializers.BooleanField(read_only=True)
    roles = serializers.SerializerMethodField()
    role_ids = serializers.SerializerMethodField()

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
            "is_admin",
            "is_care_staff",
            "is_active",
            "date_joined",
            "last_login",
            "updated_at",
            "roles",
            "role_ids",
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
            "has_verified_badge",
        ]

    def get_roles(self, instance):
        return assignment_roles_representation(instance)["roles"]

    def get_role_ids(self, instance):
        return assignment_roles_representation(instance)["role_ids"]

    def create(self, validated_data):
        """Admins will create Associates"""

    def update(self, instance: AssociateCenterAssignment, validated_data):
        """Associates can update their profiles"""
        associate_data = validated_data.pop("associate", {})
        user_data = associate_data.pop("user", {})
        user_data.pop("email", None)
        user_data.pop("phone", None)

        user = instance.associate.user

        validated_data.pop("is_admin", None)
        validated_data.pop("is_care_staff", None)
        validated_data.pop("is_external", None)
        validated_data.pop("is_active", None)

        with transaction.atomic():
            for key, value in associate_data.items():
                setattr(instance.associate, key, value)
            instance.associate.save(
                update_fields=[*associate_data.keys(), "updated_at"]
            )
            for key, value in user_data.items():
                setattr(user, key, value)
            user.save(update_fields=[*user_data.keys(), "updated_at"])
            return super().update(instance, validated_data)


class AdminAssociateCenterLinkSerializer(BaseSerializer):
    """Serializer to link/delink associates to a center by admin"""

    add = CenterIDSerializer(many=True, required=False, write_only=True)
    remove = CenterIDSerializer(many=True, required=False, write_only=True)

    @classmethod
    def retrieve_invalid_center_ids(cls, input_center_ids):
        existing_center_ids = set(
            Center.objects.filter(id__in=set(input_center_ids)).values_list(
                "id", flat=True
            )
        )
        invalid_ids = set(input_center_ids) - existing_center_ids
        return invalid_ids

    def validate(self, attrs):
        add_centers_by_id = {
            center_data["id"]: center_data for center_data in attrs.get("add", [])
        }
        add_centers = list(add_centers_by_id.values())
        add_center_ids = list(add_centers_by_id)
        remove_center_ids = list(
            dict.fromkeys(
                center_data["id"] for center_data in attrs.get("remove", [])
            )
        )

        if not add_center_ids and not remove_center_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        if add_center_ids:
            invalid_ids = self.retrieve_invalid_center_ids(add_center_ids)
            if invalid_ids:
                raise serializers.ValidationError(
                    {
                        "add": (
                            f"Centers not found: "
                            f"{[str(center_id) for center_id in invalid_ids]}"
                        )
                    }
                )

        invalid_flag_center_ids = [
            center_data["id"]
            for center_data in add_centers
            if not center_data["is_admin"] and not center_data["is_care_staff"]
        ]
        if invalid_flag_center_ids:
            raise serializers.ValidationError(
                {
                    "add": (
                        "At least one of 'is_admin' or 'is_care_staff' must be "
                        f"true for centers: "
                        f"{[str(center_id) for center_id in invalid_flag_center_ids]}"
                    )
                }
            )

        if remove_center_ids:
            invalid_ids = self.retrieve_invalid_center_ids(remove_center_ids)
            if invalid_ids:
                raise serializers.ValidationError(
                    {
                        "remove": (
                            f"Centers not found: "
                            f"{[str(center_id) for center_id in invalid_ids]}"
                        )
                    }
                )

        attrs["add"] = add_centers
        attrs["remove"] = remove_center_ids

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        associate = validated_data.pop("associate", None)
        created_by = validated_data.pop("created_by", None)

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
                    center_id=center_data["id"],
                    is_admin=center_data["is_admin"],
                    is_care_staff=center_data["is_care_staff"],
                    created_by=created_by,
                )
                for center_data in add_centers
            ]
            AssociateCenterAssignment.objects.bulk_create(
                assignments,
                update_conflicts=True,
                update_fields=["is_admin", "is_care_staff"],
                unique_fields=["associate", "center"],
            )

        affected_center_ids = [
            center_data["id"] for center_data in add_centers
        ] + list(remove_center_ids)
        refresh_staff_counts(affected_center_ids)
        update_associate_centers_count(associate.pk)

        return associate


class AssociateCenterSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="center.id", read_only=True)
    code = serializers.CharField(source="center.code", read_only=True)
    name = serializers.CharField(source="center.name", read_only=True)
    image = serializers.ImageField(source="center.image", read_only=True)
    address = serializers.CharField(source="center.address", read_only=True)
    address_line_1 = serializers.CharField(
        source="center.address_line_1", read_only=True
    )
    address_line_2 = serializers.CharField(
        source="center.address_line_2", read_only=True
    )
    city = serializers.CharField(source="center.city", read_only=True)
    state = serializers.CharField(source="center.state", read_only=True)
    country = serializers.CharField(source="center.country", read_only=True)
    pincode = serializers.CharField(source="center.pincode", read_only=True)
    phone = serializers.CharField(source="center.phone", read_only=True)
    email = serializers.EmailField(source="center.email", read_only=True)
    contact_person = serializers.CharField(
        source="center.contact_person", read_only=True
    )
    modes = serializers.CharField(source="center.modes", read_only=True)
    status = serializers.CharField(source="center.status", read_only=True)
    created_at = serializers.DateTimeField(
        source="center.created_at", read_only=True
    )
    updated_at = serializers.DateTimeField(
        source="center.updated_at", read_only=True
    )
    is_active = serializers.BooleanField(source="center.is_active", read_only=True)
    is_admin = serializers.BooleanField(read_only=True)
    is_care_staff = serializers.BooleanField(read_only=True)

    class Meta:
        model = AssociateCenterAssignment
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
            "created_at",
            "updated_at",
            "is_active",
            "is_admin",
            "is_care_staff",
        ]


class BaseCenterAssociateSerializer(BaseModelSerializer):
    """Serializer to list Associates liked to a center"""

    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    email = serializers.EmailField(source="associate.user.email", read_only=True)
    phone = PhoneNumberSerializerField(
        source="associate.user.phone", read_only=True, region=None
    )
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
    date_joined = serializers.DateField(
        source="associate.date_joined", required=False, allow_null=True
    )
    is_admin = serializers.BooleanField(read_only=True)
    is_care_staff = serializers.BooleanField(read_only=True)
    exists = serializers.BooleanField(read_only=True)

    # Nested objects
    roles = serializers.SerializerMethodField()
    role_ids = serializers.SerializerMethodField()
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
            "is_care_staff",
            "exists",
            "date_joined",
            "roles",
            "role_ids",
            "created_by",
        ]

    def get_roles(self, instance):
        return assignment_roles_representation(instance)["roles"]

    def get_role_ids(self, instance):
        return assignment_roles_representation(instance)["role_ids"]

    def to_representation(self, instance: AssociateCenterAssignment):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep


class CenterAssociateSerializer(
    AssociateSourceMixinSerializer,
    BasePasswordCheckOptionalSerializer,
    BaseModelSerializer,
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
    date_joined = serializers.DateField(
        source="associate.date_joined", required=False, allow_null=True
    )
    roles = serializers.SerializerMethodField()
    role_ids = AssignmentRoleIdsField()

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
            "is_care_staff",
            "is_primary",
            "is_active",
            "date_joined",
            # Write only fields
            "role_ids",
            "password1",
            "password2",
            "send_password_link",
            "created_at",
            "updated_at",
            "roles",
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
            "has_verified_badge",
            "created_by",
        ]

    def validate(self, attrs):
        if not attrs.get("is_admin", False) and not attrs.get(
            "is_care_staff", False
        ):
            raise serializers.ValidationError(
                "At least one of 'is_admin' or 'is_care_staff' must be true."
            )
        return attrs

    def create(self, validated_data):
        """Allows center admins or Associates with FULL feature to add associates"""
        center = validated_data.pop("center", None)
        if not center:
            raise serializers.ValidationError("Invalid Center ID provided.")
        send_password_link = validated_data.pop("send_password_link", False)

        associate_data = validated_data.pop("associate", {})
        user_data = associate_data.pop("user", {})
        role_ids = validated_data.pop("role_ids", serializers.empty)
        if role_ids is serializers.empty:
            role_ids = None

        is_admin = validated_data.pop("is_admin", False)
        is_care_staff = validated_data.pop("is_care_staff", False)

        email = user_data.get("email")
        password1 = None
        roles = []

        errors = {}
        if email and User.objects.filter(email__iexact=email).exists():
            errors["email"] = "User with this email already exists."
        if errors:
            raise serializers.ValidationError(errors)

        if is_admin and role_ids:
            raise serializers.ValidationError(
                {"role_ids": "System users cannot have associate roles"}
            )

        if not is_admin and role_ids is not None:
            roles = resolve_center_roles(center, role_ids or [])
        if not send_password_link:
            password1 = self.get_validated_password(validated_data)

        validated_data["is_admin"] = is_admin
        validated_data["is_care_staff"] = is_care_staff
        with transaction.atomic():
            user = User.objects.create_user(**user_data, password=password1, phone=None)

            associate = Associate.objects.create(user=user, **associate_data)
            create_associate_user_account(associate)

            assignment = AssociateCenterAssignment.objects.create(
                associate=associate,
                center=center,
                **validated_data,
            )
            if role_ids is not None:
                replace_assignment_roles(assignment, roles)

            increment_staff_count(assignment.center.pk)
            update_associate_centers_count(associate.pk)
            increment_organization_admins_count()
            if send_password_link:
                send_registration_code(user)
        return assignment

    def get_roles(self, instance):
        return assignment_roles_representation(instance)["roles"]

    def update(self, instance: AssociateCenterAssignment, validated_data):
        """Update not allowed in this serializer"""
        pass

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep


class CenterAssociateDetailSerializer(
    AssociateSourceMixinSerializer, BaseModelSerializer
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

    roles = serializers.SerializerMethodField()
    role_ids = AssignmentRoleIdsField()

    # Assignment fields already at root
    # is_admin, mode, is_primary come from the model directly

    is_active = serializers.BooleanField(
        source="associate.user.is_active", required=False
    )
    date_joined = serializers.DateField(
        source="associate.date_joined", required=False, allow_null=True
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
            # Roles (nested + ids)
            "roles",
            "role_ids",
            # Assignment fields (native)
            "is_admin",
            "is_care_staff",
            "is_primary",
            "is_active",
            "date_joined",
            "created_at",
            "updated_at",
            # Associate profile fields (from mixin)
            "title",
            "description",
            "tagline",
            "experience",
            "qualifications",
            "professions",
            "has_verified_badge",
        ]

    def get_roles(self, instance):
        return assignment_roles_representation(instance)["roles"]

    def update(self, instance: AssociateCenterAssignment, validated_data):
        """Update user fields, associate fields, and roles on the assignment."""
        associate_data = validated_data.pop("associate", {})
        user_data = associate_data.pop("user", {})
        user_data.pop("phone", None)
        role_ids = validated_data.pop("role_ids", serializers.empty)

        user = instance.associate.user
        is_active = user_data.get("is_active", user.is_active)
        associate_data["is_active"] = is_active
        email = user_data.get("email")

        errors = {}
        if email:
            user_exists = (
                User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists()
            )
            if user_exists:
                errors["email"] = "User with this email already exists."

        if errors:
            raise serializers.ValidationError(errors)

        will_be_admin = validated_data.get("is_admin", instance.is_admin)
        if will_be_admin and role_ids is not serializers.empty and role_ids:
            raise serializers.ValidationError(
                {"role_ids": "Roles cannot be assigned to admin associates."}
            )

        roles = []
        replace_roles = will_be_admin
        if not will_be_admin and role_ids is not serializers.empty:
            roles = resolve_center_roles(instance.center, role_ids or [])
            replace_roles = True

        was_active = user.is_active

        with transaction.atomic():
            if user_data:
                for key, value in user_data.items():
                    setattr(user, key, value)
                user.save(update_fields=[*user_data.keys(), "updated_at"])

            if associate_data:
                associate = instance.associate
                for key, value in associate_data.items():
                    setattr(associate, key, value)
                associate.save(update_fields=[*associate_data.keys(), "updated_at"])

            if "is_active" in user_data:
                is_now_active = user_data["is_active"]
                if not is_now_active and was_active:
                    increment_inactive_staff_count(instance.center.pk)
                if is_now_active and not was_active:
                    decrement_inactive_staff_count(instance.center.pk)
                if is_now_active != was_active:
                    update_organization_staff_count()
            instance = super().update(instance, validated_data)
            if replace_roles:
                replace_assignment_roles(instance, roles)
        return instance

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep


class AssociateCenterPermissionSerializer(BaseModelSerializer):
    roles = serializers.SerializerMethodField()
    role_ids = serializers.SerializerMethodField()

    class Meta:
        model = AssociateCenterAssignment
        fields = [
            "roles",
            "role_ids",
            "is_admin",
            "is_care_staff",
            "mode",
            "is_primary",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_roles(self, instance):
        return assignment_roles_representation(instance)["roles"]

    def get_role_ids(self, instance):
        return assignment_roles_representation(instance)["role_ids"]


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

        attrs["add"] = dedupe_ids(add_ids)
        attrs["remove"] = dedupe_ids(remove_ids)
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
