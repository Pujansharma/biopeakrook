from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from core.utils.serializers import BaseModelSerializer
from products.models import Product
from test_kit_assignment.models import TestKitAssignment
from test_kit_assignment.utils.constants import (
    TestKitAssignmentStatus,
    TestKitHandoverType,
)
from test_kit_assignment.utils.db import (
    customer_profile_has_active_test_kit,
    customer_profile_has_completed_pre_consultation,
)


class ConflictError(APIException):
    status_code = 409
    default_detail = "Conflict."
    default_code = "conflict"


class EligibleCustomerProfileSerializer(BaseModelSerializer):
    name = serializers.SerializerMethodField()
    phone = serializers.CharField(source="customer.user.phone", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["id", "name", "phone"]

    @staticmethod
    def get_name(instance: CustomerProfile) -> str:
        return instance.get_full_name()


class TestKitAssignmentProductNameSerializer(BaseModelSerializer):
    class Meta:
        model = Product
        fields = ["name"]


class TestKitAssignmentHistorySerializer(BaseModelSerializer):
    products = TestKitAssignmentProductNameSerializer(many=True, read_only=True)
    customer = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    handover_type = serializers.CharField(read_only=True)

    class Meta:
        model = TestKitAssignment
        fields = [
            "handover_type",
            "assigned_on",
            "is_kit_journey_visible",
            "products",
            "customer",
            "clinic",
            "created_by",
        ]

    def to_representation(self, instance: TestKitAssignment) -> dict:
        return {
            "handover_type": instance.handover_type,
            "assigned_on": serializers.DateTimeField().to_representation(
                instance.assigned_on
            ),
            "is_kit_journey_visible": instance.is_kit_journey_visible,
            "products": TestKitAssignmentProductNameSerializer(
                instance.products.all(),
                many=True,
            ).data,
            "customer": self.get_customer(instance),
            "clinic": self.get_clinic(instance),
            "created_by": self.get_created_by(instance),
        }

    @staticmethod
    def get_customer(instance: TestKitAssignment) -> dict:
        profile = instance.assigned_to
        return {
            "name": profile.get_full_name(),
            "phone": str(profile.customer.user.phone)
            if profile.customer.user.phone
            else None,
        }

    @staticmethod
    def get_clinic(instance: TestKitAssignment) -> dict | None:
        if instance.clinic is None:
            return None
        return {"name": instance.clinic.name}

    @staticmethod
    def get_created_by(instance: TestKitAssignment) -> dict | None:
        if instance.created_by is None:
            return None
        return {"name": instance.created_by.get_full_name()}


class TestKitAssignmentCreateSerializer(BaseModelSerializer):
    assigned_to = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        write_only=True,
    )
    products = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        write_only=True,
    )
    clinic_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        write_only=True,
    )
    assigned_on = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    is_kit_journey_visible = serializers.BooleanField(required=False, default=True)

    class Meta:
        model = TestKitAssignment
        fields = [
            "assigned_to",
            "handover_type",
            "is_kit_journey_visible",
            "products",
            "clinic_id",
            "assigned_on",
            "notes",
        ]

    def validate_handover_type(self, value: str) -> str:
        valid_values = {choice.value for choice in TestKitHandoverType}
        if value not in valid_values:
            raise serializers.ValidationError("Invalid handover type.")
        return value

    def validate_assigned_to(self, value: list) -> list:
        unique_profile_ids = list(dict.fromkeys(value))
        if len(unique_profile_ids) != len(value):
            raise serializers.ValidationError(
                "Duplicate customer profiles are not allowed."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        handover_type = attrs["handover_type"]
        clinic_id = attrs.get("clinic_id")
        assigned_on = attrs.get("assigned_on")
        notes = attrs.get("notes")

        if handover_type == TestKitHandoverType.DELIVERY:
            if clinic_id is not None:
                raise serializers.ValidationError(
                    {"clinic_id": "Must be null when handover_type is delivery."}
                )
            attrs["clinic"] = None
            attrs["notes"] = None
            attrs["assigned_on"] = timezone.now()
            return attrs

        if clinic_id is None:
            raise serializers.ValidationError(
                {"clinic_id": "This field is required for manual_handover."}
            )
        if assigned_on is None:
            raise serializers.ValidationError(
                {"assigned_on": "This field is required for manual_handover."}
            )

        clinic = Center.objects.filter(pk=clinic_id, is_active=True).first()
        if clinic is None:
            raise serializers.ValidationError({"clinic_id": "Invalid clinic."})

        attrs["clinic"] = clinic
        if notes == "":
            attrs["notes"] = None
        return attrs

    @staticmethod
    def get_customer_profiles_or_error(profile_ids: list) -> list[CustomerProfile]:
        customer_profiles = list(
            CustomerProfile.objects.select_related("customer__user").filter(
                pk__in=profile_ids
            )
        )
        profiles_by_id = {
            customer_profile.pk: customer_profile
            for customer_profile in customer_profiles
        }
        missing_profile_ids = [
            profile_id
            for profile_id in profile_ids
            if profile_id not in profiles_by_id
        ]
        if missing_profile_ids:
            raise serializers.ValidationError({"assigned_to": "Invalid customer profile."})
        return [profiles_by_id[profile_id] for profile_id in profile_ids]

    @staticmethod
    def assert_customer_profile_eligible(customer_profile: CustomerProfile) -> None:
        if not customer_profile_has_completed_pre_consultation(customer_profile):
            raise ConflictError(
                "Customer profile has not completed pre-consultation."
            )
        if customer_profile_has_active_test_kit(customer_profile):
            raise ConflictError(
                "Customer profile already has an active test-kit assignment."
            )

    @staticmethod
    def get_products_or_error(product_ids: list) -> list[Product]:
        unique_product_ids = list(dict.fromkeys(product_ids))
        if len(unique_product_ids) != len(product_ids):
            raise serializers.ValidationError(
                {"products": "Duplicate products are not allowed."}
            )
        products = list(
            Product.objects.filter(pk__in=unique_product_ids, is_active=True)
        )
        if len(products) != len(unique_product_ids):
            raise serializers.ValidationError(
                {"products": "All products must exist and be active."}
            )
        return products

    def create(self, validated_data: dict) -> list[TestKitAssignment]:
        product_ids = validated_data.pop("products")
        validated_data.pop("clinic_id", None)
        assigned_to_ids = validated_data.pop("assigned_to")

        customer_profiles = self.get_customer_profiles_or_error(assigned_to_ids)
        for customer_profile in customer_profiles:
            self.assert_customer_profile_eligible(customer_profile)
        products = self.get_products_or_error(product_ids)

        request = self.context["request"]
        try:
            with transaction.atomic():
                assignments = []
                for customer_profile in customer_profiles:
                    assignment = TestKitAssignment.objects.create(
                        assigned_to=customer_profile,
                        handover_type=validated_data["handover_type"],
                        is_kit_journey_visible=validated_data.get(
                            "is_kit_journey_visible",
                            True,
                        ),
                        clinic=validated_data.get("clinic"),
                        assigned_on=validated_data["assigned_on"],
                        notes=validated_data.get("notes"),
                        status=TestKitAssignmentStatus.ACTIVE,
                        created_by=request.user,
                    )
                    assignment.products.set(products)
                    assignments.append(assignment)
        except IntegrityError as error:
            raise ConflictError(
                "Customer profile already has an active test-kit assignment."
            ) from error

        return assignments

    def to_representation(self, instance: list[TestKitAssignment]) -> list[dict]:
        return TestKitAssignmentHistorySerializer(
            instance,
            many=True,
            context=self.context,
        ).data
