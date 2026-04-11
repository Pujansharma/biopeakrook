from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.customers.models import (
    Customer,
    CustomerCenterAssignment,
    CustomerProfile,
)
from accounts.customers.utils.db import create_customer_user_account
from accounts.users.models import User
from accounts.users.utils.constants import Gender
from accounts.utils.db import get_user_account_type
from accounts.verifications.models import PhoneVerification
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer

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

        if profile.is_primary:
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
    is_primary = serializers.BooleanField(
        source="customer_profile.is_primary", read_only=True
    )

    class Meta:
        model = CustomerCenterAssignment
        fields = [
            "id",
            "phone",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "image",
            "is_primary",
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

        user = User.objects.filter(phone__iexact=phone).first()
        if user:
            account_type = get_user_account_type(user)
            raise serializers.ValidationError(
                {
                    "phone": f"A user with this phone number already exists as an {account_type} account."
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
                email=None, password=None, phone=phone, **profile_data
            )
            customer = Customer.objects.create(user=user)
            profile = CustomerProfile.objects.create(
                customer=customer, is_primary=True, **profile_data
            )
            create_customer_user_account(customer)

            assignment = CustomerCenterAssignment.objects.create(
                customer_profile=profile,
                center_id=center_id,
            )

        return assignment

    def update(self, instance: CustomerCenterAssignment, validated_data):
        profile_wrapper = validated_data.pop("customer_profile", {})
        customer_wrapper = profile_wrapper.pop("customer", {})
        user_wrapper = customer_wrapper.pop("user", {})
        phone = user_wrapper.get("phone")

        if phone:
            current_user = instance.customer_profile.customer.user
            if (
                User.objects.filter(phone__iexact=phone)
                .exclude(pk=current_user.pk)
                .exists()
            ):
                raise serializers.ValidationError(
                    {"phone": "A user with this phone number already exists."}
                )
            current_user.phone = phone
            current_user.save(update_fields=["phone", "updated_at"])

        if profile_wrapper:
            profile = instance.customer_profile
            for key, value in profile_wrapper.items():
                setattr(profile, key, value)
            profile.save()

            if profile.is_primary:
                user = profile.customer.user
                for field in PROFILE_FIELDS:
                    setattr(user, field, getattr(profile, field))
                user.save(update_fields=[*PROFILE_FIELDS, "updated_at"])

        return instance

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        if "gender" in self.get_fields():
            rep["gender"] = instance.customer_profile.get_gender_display()
        return rep


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
