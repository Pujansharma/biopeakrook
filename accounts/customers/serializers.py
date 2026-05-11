from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.associates.serializers import (
    BaseAssociateSerializer,
    BaseAssociateRoleSerializer,
)
from accounts.centers.models import Center
from accounts.centers.serializers import MinimumCenterSerializer
from accounts.centers.utils.db import (
    increment_customer_count,
    decrement_customer_count,
    increment_inactive_customer_count,
    decrement_inactive_customer_count,
)
from accounts.customers.models import (
    Customer,
    CustomerCenterAssignment,
    CustomerProfile,
    CustomerAssociateAssignment,
)
from accounts.customers.utils.db import (
    create_customer_user_account,
    increment_centers_count,
    decrement_centers_count,
    increment_external_centers_count,
    decrement_external_centers_count,
    compute_customer_profile_center_counts,
)
from accounts.users.models import User
from accounts.users.serializers import BaseUserSerializer
from accounts.users.utils.constants import Gender
from accounts.utils.db import get_user_account_type
from accounts.verifications.models import PhoneVerification
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer, BaseSerializer

PROFILE_FIELDS = ["first_name", "last_name", "gender", "date_of_birth", "image"]


class CustomerAccountSerializer(BaseModelSerializer):
    """Serializer for customers to view and update their account details"""

    phone = PhoneNumberSerializerField(source="user.phone", read_only=True)
    phone_otp = serializers.CharField(write_only=True, required=False)
    email = serializers.EmailField(source="user.email", required=False, allow_null=True)
    email_otp = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Customer
        fields = [
            "phone",
            "phone_otp",
            "email",
            "email_otp",
        ]

    def update(self, instance: Customer, validated_data):
        phone = validated_data.get("phone", None)
        phone_otp = validated_data.get("phone_otp", None)
        if phone and not phone_otp:
            raise serializers.ValidationError(
                {"phone_otp": "OTP is required for phone validation"}
            )

        phone_validation = PhoneVerification.objects.filter(
            phone=phone, expires_at__gte=timezone.localtime(), is_active=True
        ).first()
        if not phone_validation:
            raise serializers.ValidationError(
                {"phone": "Invalid Phone number provided"}
            )

        email = validated_data.get("email", None)
        email_otp = validated_data.get("email_otp", None)
        if email and not email_otp:
            raise serializers.ValidationError({"email_otp": "Invalid OTP provided"})

        user_data = validated_data.pop("user", {})

        if user_data:
            user = instance.user
            for key, value in user_data.items():
                setattr(user, key, value)
            user.save()
        return instance


class BaseCustomerProfileSerializer(BaseModelSerializer):
    email = serializers.EmailField(source="customer.user.email", read_only=True)
    phone = PhoneNumberSerializerField(source="customer.user.phone", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_main",
            "is_onboarding_complete",
            "created_at",
            "updated_at",
        ]


class CustomerProfileWithCenterSerializer(BaseCustomerProfileSerializer):
    home_center = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "home_center",
            "created_at",
            "updated_at",
        ]

    def get_home_center(self, instance):
        assignments = getattr(instance, "primary_center_assignments", None)
        if not assignments:
            return None
        return MinimumCenterSerializer(assignments[0].center, context=self.context).data


class CustomerProfileSerializer(BaseModelSerializer):
    """Serializer for customers to view and update profile details"""

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_primary",
            "is_onboarding_complete",
            "created_at",
            "updated_at",
        ]

    def update(self, instance, validated_data):
        profile: CustomerProfile = super().update(instance, validated_data)

        if profile.is_main:
            user = profile.customer.user
            for field in PROFILE_FIELDS:
                setattr(user, field, getattr(profile, field))
            user.save(update_fields=[*PROFILE_FIELDS, "updated_at"])

        return profile

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.get_gender_display()
        return rep


class CenterCustomerProfileSerializer(BaseModelSerializer):
    """Serializer for center admins to list, create, and update customer profiles"""

    id = serializers.UUIDField(source="customer_profile.id", read_only=True)
    email = serializers.EmailField(
        source="customer_profile.customer.user.email", required=True
    )
    phone = PhoneNumberSerializerField(
        source="customer_profile.customer.user.phone", required=True
    )
    first_name = serializers.CharField(source="customer_profile.first_name")
    last_name = serializers.CharField(
        source="customer_profile.last_name", required=False, allow_null=True
    )
    gender = serializers.ChoiceField(
        source="customer_profile.gender",
        choices=Gender.CHOICES,
        required=False,
        allow_null=True,
    )
    date_of_birth = serializers.DateField(
        source="customer_profile.date_of_birth", required=False, allow_null=True
    )
    image = serializers.ImageField(
        source="customer_profile.image", required=False, allow_null=True
    )
    is_main = serializers.BooleanField(
        source="customer_profile.is_main", read_only=True
    )

    is_active = serializers.BooleanField(
        source="customer_profile.customer.user.is_active", read_only=True
    )
    is_primary = serializers.BooleanField(read_only=True)
    centers_count = serializers.IntegerField(
        source="customer_profile.centers_count", read_only=True, default=0
    )
    external_centers_count = serializers.IntegerField(
        source="customer_profile.external_centers_count", read_only=True, default=0
    )

    class Meta:
        model = CustomerCenterAssignment
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_main",
            "is_primary",
            "is_active",
            "centers_count",
            "external_centers_count",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        center_id = validated_data.pop("center_id", None)
        if not center_id:
            raise serializers.ValidationError("Invalid Center ID provided.")
        profile_wrapper = validated_data.pop("customer_profile", {})
        customer_wrapper = profile_wrapper.pop("customer", {})
        user_wrapper = customer_wrapper.pop("user", {})
        phone = user_wrapper.get("phone")
        email = user_wrapper.get("email")

        phone_user = User.objects.filter(phone__iexact=phone).first()
        if phone_user:
            account_type = get_user_account_type(phone_user)
            raise serializers.ValidationError(
                {
                    "phone": f"A user with this phone number already exists as an {account_type} account."
                }
            )
        email_user = User.objects.filter(email__iexact=email).first()
        if email_user:
            account_type = get_user_account_type(email_user)
            raise serializers.ValidationError(
                {
                    "email": f"A user with this email already exists as an {account_type} account."
                }
            )

        profile_data = {
            "first_name": profile_wrapper.get("first_name"),
            "last_name": profile_wrapper.get("last_name"),
            "gender": profile_wrapper.get("gender"),
            "date_of_birth": profile_wrapper.get("date_of_birth"),
            "image": profile_wrapper.get("image"),
        }

        with transaction.atomic():
            user = User.objects.create_user(
                email=email, password=None, phone=phone, **profile_data
            )
            customer = Customer.objects.create(user=user)
            profile = CustomerProfile.objects.create(
                customer=customer, is_main=True, **profile_data
            )
            create_customer_user_account(customer)

            if CustomerCenterAssignment.objects.filter(
                    customer_profile=profile, is_primary=True
            ).exists():
                raise serializers.ValidationError(
                    "This profile already has a primary center assigned."
                )
            assignment = CustomerCenterAssignment.objects.create(
                customer_profile=profile, center_id=center_id, is_primary=True
            )
            increment_customer_count(center_id)
            increment_centers_count(profile.pk)

        return assignment

    def update(self, instance, validated_data):
        """Update not allowed in this serializer"""
        pass

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.customer_profile.get_gender_display()
        return rep


class CenterCustomerProfileHomeCenterSerializer(BaseModelSerializer):
    """Serializer for center admins to list, create, and update customer profiles"""

    id = serializers.UUIDField(source="customer_profile.id", read_only=True)
    email = serializers.EmailField(
        source="customer_profile.customer.user.email", required=True
    )
    phone = PhoneNumberSerializerField(
        source="customer_profile.customer.user.phone", required=True
    )
    first_name = serializers.CharField(source="customer_profile.first_name")
    last_name = serializers.CharField(
        source="customer_profile.last_name", required=False, allow_null=True
    )
    gender = serializers.ChoiceField(
        source="customer_profile.gender",
        choices=Gender.CHOICES,
        required=False,
        allow_null=True,
    )
    date_of_birth = serializers.DateField(
        source="customer_profile.date_of_birth", required=False, allow_null=True
    )
    image = serializers.ImageField(
        source="customer_profile.image", required=False, allow_null=True
    )
    is_main = serializers.BooleanField(
        source="customer_profile.is_main", read_only=True
    )

    is_active = serializers.BooleanField(
        source="customer_profile.customer.user.is_active", read_only=True
    )
    is_primary = serializers.BooleanField(read_only=True)
    home_center = serializers.SerializerMethodField(read_only=True)
    centers_count = serializers.IntegerField(
        source="customer_profile.centers_count", read_only=True, default=0
    )
    external_centers_count = serializers.IntegerField(
        source="customer_profile.external_centers_count", read_only=True, default=0
    )

    class Meta:
        model = CustomerCenterAssignment
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_main",
            "is_primary",
            "is_active",
            "centers_count",
            "external_centers_count",
            "created_at",
            "updated_at",
            "home_center"
        ]

    def get_home_center(self, instance):
        assignments = getattr(instance.customer_profile, "primary_center_assignments", None)
        if not assignments:
            return None
        return MinimumCenterSerializer(assignments[0].center, context=self.context).data

    def create(self, validated_data):
        center_id = validated_data.pop("center_id", None)
        if not center_id:
            raise serializers.ValidationError("Invalid Center ID provided.")
        profile_wrapper = validated_data.pop("customer_profile", {})
        customer_wrapper = profile_wrapper.pop("customer", {})
        user_wrapper = customer_wrapper.pop("user", {})
        phone = user_wrapper.get("phone")
        email = user_wrapper.get("email")

        phone_user = User.objects.filter(phone__iexact=phone).first()
        if phone_user:
            account_type = get_user_account_type(phone_user)
            raise serializers.ValidationError(
                {
                    "phone": f"A user with this phone number already exists as an {account_type} account."
                }
            )
        email_user = User.objects.filter(email__iexact=email).first()
        if email_user:
            account_type = get_user_account_type(email_user)
            raise serializers.ValidationError(
                {
                    "email": f"A user with this email already exists as an {account_type} account."
                }
            )

        profile_data = {
            "first_name": profile_wrapper.get("first_name"),
            "last_name": profile_wrapper.get("last_name"),
            "gender": profile_wrapper.get("gender"),
            "date_of_birth": profile_wrapper.get("date_of_birth"),
            "image": profile_wrapper.get("image"),
        }

        with transaction.atomic():
            user = User.objects.create_user(
                email=email, password=None, phone=phone, **profile_data
            )
            customer = Customer.objects.create(user=user)
            profile = CustomerProfile.objects.create(
                customer=customer, is_main=True, **profile_data
            )
            create_customer_user_account(customer)

            if CustomerCenterAssignment.objects.filter(
                    customer_profile=profile, is_primary=True
            ).exists():
                raise serializers.ValidationError(
                    "This profile already has a primary center assigned."
                )
            assignment = CustomerCenterAssignment.objects.create(
                customer_profile=profile, center_id=center_id, is_primary=True
            )
            increment_customer_count(center_id)
            increment_centers_count(profile.pk)

        return assignment

    def update(self, instance, validated_data):
        """Update not allowed in this serializer"""
        pass

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.customer_profile.get_gender_display()
        return rep


class BaseCustomerAssignedCenterSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="center.id", read_only=True)
    name = serializers.CharField(source="center.name", read_only=True)

    # is_primary = serializers.BooleanField(source="customer_profile.is_primary", read_only=True)
    # is_active = serializers.BooleanField(source="customer_profile.customer.user.is_active")

    class Meta:
        model = CustomerCenterAssignment
        fields = ["id", "name", "is_primary", "created_at"]


class CenterCustomerProfileDetailSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="customer_profile.id", read_only=True)
    email = serializers.EmailField(
        source="customer_profile.customer.user.email", required=True
    )
    phone = PhoneNumberSerializerField(
        source="customer_profile.customer.user.phone", required=True
    )
    first_name = serializers.CharField(source="customer_profile.first_name")
    last_name = serializers.CharField(
        source="customer_profile.last_name", required=False, allow_null=True
    )
    gender = serializers.ChoiceField(
        source="customer_profile.gender",
        choices=Gender.CHOICES,
        required=False,
        allow_null=True,
    )
    date_of_birth = serializers.DateField(
        source="customer_profile.date_of_birth", required=False, allow_null=True
    )
    image = serializers.ImageField(
        source="customer_profile.image", required=False, allow_null=True
    )
    is_main = serializers.BooleanField(
        source="customer_profile.is_main", read_only=True
    )
    is_active = serializers.BooleanField(
        source="customer_profile.customer.user.is_active"
    )
    centers_count = serializers.IntegerField(
        source="customer_profile.centers_count", read_only=True, default=0
    )
    external_centers_count = serializers.IntegerField(
        source="customer_profile.external_centers_count", read_only=True, default=0
    )

    class Meta:
        model = CustomerCenterAssignment
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_main",
            "is_primary",
            "is_active",
            "centers_count",
            "external_centers_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_main", "is_primary", "centers_count", "external_centers_count"]

    def update(self, instance: CustomerCenterAssignment, validated_data):
        profile_wrapper = validated_data.pop("customer_profile", {})
        customer_wrapper = profile_wrapper.pop("customer", {})
        user_wrapper = customer_wrapper.pop("user", {})
        phone = user_wrapper.get("phone")
        email = user_wrapper.get("email")

        is_active = user_wrapper.get("is_active", None)
        if is_active is not None:
            profile_wrapper["is_active"] = is_active

        user = instance.customer_profile.customer.user
        if phone:
            if User.objects.filter(phone__iexact=phone).exclude(pk=user.pk).exists():
                raise serializers.ValidationError(
                    {"phone": "A user with this phone number already exists."}
                )

        if email:
            if User.objects.filter(phone__iexact=phone).exclude(pk=user.pk).exists():
                raise serializers.ValidationError(
                    {"phone": "A user with this phone number already exists."}
                )

        if profile_wrapper:
            profile = instance.customer_profile
            for key, value in profile_wrapper.items():
                setattr(profile, key, value)
            profile.save(update_fields=[*list(profile_wrapper.keys()), "updated_at"])

            if profile.is_main:
                for field in PROFILE_FIELDS:
                    setattr(user, field, getattr(profile, field))

            for key, value in user_wrapper.items():
                setattr(user, key, value)

            user.save(
                update_fields=[
                    *PROFILE_FIELDS,
                    *list(user_wrapper.keys()),
                    "updated_at",
                ]
            )

        if "is_active" in user_wrapper:
            if not user.is_active:
                increment_inactive_customer_count(instance.center.pk)
            if user.is_active:
                decrement_inactive_customer_count(instance.center.pk)

        return instance


class CustomerRegistrationSerializer(BaseModelSerializer):
    phone = PhoneNumberSerializerField(write_only=True)
    first_name = serializers.CharField()
    last_name = serializers.CharField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=Gender.CHOICES, required=False, allow_null=True
    )
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = Customer
        fields = [
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
        ]

    def validate_phone(self, phone):
        if User.objects.filter(phone__iexact=phone).exists():
            raise serializers.ValidationError(
                "A user with this phone number already exists."
            )

        verification = PhoneVerification.objects.filter(
            phone__iexact=phone,
            purpose=PhoneVerification.PURPOSE_REGISTER,
            verified_at__isnull=False,
            expires_at__gte=timezone.now(),
        ).first()

        if not verification:
            raise serializers.ValidationError(
                "Phone number is not verified or verification has expired."
            )

        self.context["verification"] = verification
        return phone

    def create(self, validated_data):
        phone = validated_data.pop("phone")
        verification = self.context["verification"]

        profile_data = {
            "first_name": validated_data.pop("first_name"),
            "last_name": validated_data.pop("last_name", None),
            "gender": validated_data.pop("gender", None),
            "date_of_birth": validated_data.pop("date_of_birth", None),
        }

        with transaction.atomic():
            user = User.objects.create_user(
                email=None, password=None, phone=phone, **profile_data
            )
            customer = Customer.objects.create(user=user)
            CustomerProfile.objects.create(
                customer=customer, is_primary=True, **profile_data
            )
            create_customer_user_account(customer)

            verification.is_active = False
            verification.save(update_fields=["is_active", "updated_at"])

        return customer


class AssociateIDSerializer(BaseSerializer):
    id = serializers.UUIDField(write_only=True)


class CustomerAssociateAssignmentSerializer(BaseModelSerializer):
    center_id = serializers.UUIDField(write_only=True)
    add = AssociateIDSerializer(many=True, required=False, write_only=True)
    remove = AssociateIDSerializer(write_only=True, required=False, many=True)

    class Meta:
        model = CustomerAssociateAssignment
        fields = [
            "center_id",
            "add",
            "remove",
        ]

    @classmethod
    def get_invalid_associates(cls, center_id, associate_ids):
        qs = AssociateCenterAssignment.objects.filter(
            center_id=center_id, associate_id__in=associate_ids, is_admin=False
        ).values_list("associate_id", flat=True)

        not_valid = set(associate_ids) - set(qs)
        return not_valid

    def create(self, validated_data):
        add_associate_ids = []
        remove_associate_ids = []
        center_id = validated_data.pop("center_id", None)
        customer_profile_id = validated_data.pop("customer_profile_id", None)
        created_by = validated_data.pop("created_by", None)

        add_ids = validated_data.get("add", [])
        remove_ids = validated_data.get("remove", [])

        if not center_id:
            raise serializers.ValidationError(
                {"center_id": "A valid center must be provided"}
            )
        if not customer_profile_id:
            raise serializers.ValidationError("Invalid customer ID provided")

        if not add_ids and not remove_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        if add_ids:
            add_associate_ids = [i["id"] for i in add_ids]

        if remove_ids:
            remove_associate_ids = [i["id"] for i in remove_ids]

        if add_associate_ids:
            invalid_ids = self.get_invalid_associates(center_id, add_associate_ids)
            if invalid_ids:
                raise serializers.ValidationError(
                    {
                        "add": f"Invalid IDs provided for associates: {[str(uid) for uid in invalid_ids]}"
                    }
                )
            _assignments = [
                CustomerAssociateAssignment(
                    customer_profile_id=customer_profile_id,
                    associate_id=i,
                    center_id=center_id,
                    created_by=created_by,
                )
                for i in add_associate_ids
            ]
            CustomerAssociateAssignment.objects.bulk_create(
                _assignments,
                update_conflicts=True,
                unique_fields=["customer_profile", "associate", "center"],
                update_fields=["created_by"],
            )

        if remove_associate_ids:
            invalid_ids = self.get_invalid_associates(center_id, remove_associate_ids)
            if invalid_ids:
                raise serializers.ValidationError(
                    {
                        "remove": f"Invalid IDs provided for associates: {[str(uid) for uid in invalid_ids]}"
                    }
                )
            CustomerAssociateAssignment.objects.filter(
                customer_profile_id=customer_profile_id,
                center_id=center_id,
                associate_id__in=remove_associate_ids,
            ).delete()

        return 1


class CustomerAvailableAssociateSerializer(BaseAssociateSerializer):
    exists = serializers.BooleanField(default=False, read_only=True)

    class Meta:
        model = Associate
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "image",
            "exists",
            "is_active",
        ]


class CustomerAssociateSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="associate.user.id", read_only=True)
    email = serializers.EmailField(source="associate.user.email", required=False)
    phone = PhoneNumberSerializerField(
        source="associate.user.phone", required=False, allow_null=True
    )
    first_name = serializers.CharField(
        source="associate.user.first_name", required=False, allow_null=True
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
    date_of_birth = serializers.DateField(
        source="associate.user.date_of_birth", required=False, allow_null=True
    )
    image = serializers.ImageField(
        source="associate.user.image", required=False, allow_null=True
    )
    is_active = serializers.BooleanField(
        source="user.is_active", required=False, default=True
    )
    role = BaseAssociateRoleSerializer(read_only=True)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = CustomerAssociateAssignment
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_active",
            "created_at",
            "role",
            "created_by",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.associate.user.get_gender_display()
        return rep


class CustomerProfileAvailableAssociateSerializer(BaseAssociateSerializer):
    """Serializer for listing associates available to be linked to a customer profile."""

    exists = serializers.BooleanField(read_only=True)

    class Meta:
        model = Associate
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "exists",
        ]


class CenterIDSerializer(BaseSerializer):
    id = serializers.UUIDField(write_only=True)


class CustomerCenterAssignmentSerializer(BaseModelSerializer):
    add = CenterIDSerializer(many=True, required=False, write_only=True)
    remove = CenterIDSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = CustomerCenterAssignment
        fields = ["add", "remove"]

    @classmethod
    def _invalid_center_ids(cls, center_ids: list) -> set:
        valid = set(
            Center.objects.filter(id__in=center_ids).values_list("id", flat=True)
        )
        return set(center_ids) - valid

    def validate(self, attrs):
        add_ids = [i["id"] for i in attrs.get("add", [])]
        remove_ids = [i["id"] for i in attrs.get("remove", [])]

        if not add_ids and not remove_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )
        if add_ids:
            invalid = self._invalid_center_ids(add_ids)
            if invalid:
                raise serializers.ValidationError(
                    {"add": f"Centers not found: {[str(uid) for uid in invalid]}"}
                )
        if remove_ids:
            invalid = self._invalid_center_ids(remove_ids)
            if invalid:
                raise serializers.ValidationError(
                    {"remove": f"Centers not found: {[str(uid) for uid in invalid]}"}
                )

        attrs["add"] = add_ids
        attrs["remove"] = remove_ids
        return attrs

    def create(self, validated_data):
        customer_profile_id = validated_data.pop("customer_profile_id")
        created_by = validated_data.pop("created_by")
        add_center_ids = validated_data.get("add", [])
        remove_center_ids = validated_data.get("remove", [])

        with transaction.atomic():
            if remove_center_ids:
                primary_blocked = list(
                    CustomerCenterAssignment.objects.filter(
                        customer_profile_id=customer_profile_id,
                        center_id__in=remove_center_ids,
                        is_primary=True,
                    ).values_list("center_id", flat=True)
                )
                if primary_blocked:
                    raise serializers.ValidationError(
                        {
                            "remove": f"Cannot remove primary center: {[str(uid) for uid in primary_blocked]}"
                        }
                    )
                CustomerCenterAssignment.objects.filter(
                    customer_profile_id=customer_profile_id,
                    center_id__in=remove_center_ids,
                ).delete()
                for center_id in remove_center_ids:
                    decrement_customer_count(center_id)

            if add_center_ids:
                existing_ids = set(
                    CustomerCenterAssignment.objects.filter(
                        customer_profile_id=customer_profile_id,
                        center_id__in=add_center_ids,
                    ).values_list("center_id", flat=True)
                )
                new_center_ids = [
                    cid for cid in add_center_ids if cid not in existing_ids
                ]
                CustomerCenterAssignment.objects.bulk_create(
                    [
                        CustomerCenterAssignment(
                            customer_profile_id=customer_profile_id,
                            center_id=cid,
                            created_by=created_by,
                        )
                        for cid in add_center_ids
                    ],
                    update_conflicts=True,
                    unique_fields=["customer_profile", "center"],
                    update_fields=["created_by"],
                )
                for center_id in new_center_ids:
                    increment_customer_count(center_id)

            if add_center_ids or remove_center_ids:
                compute_customer_profile_center_counts(customer_profile_id)

        return 1
