from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from products.models import Product as CatalogProduct, Provider as CatalogProvider
from test_kit_inventory.models import (
    Assignment,
    Batch,
    Item,
    Product,
    Provider,
)
from test_kit_inventory.utils import generate_test_kit_inventory_batch_id
from test_kit_inventory.utils.constants import (
    TestKitAssignmentStatus,
    TestKitHandoverType,
)
from test_kit_inventory.utils.db import (
    customer_profile_has_active_test_kit,
    customer_profile_has_completed_pre_consultation,
)

ACTIVE_TEST_KIT_UNIQUE_CONSTRAINT = "uniq_tkinv_actv_kit_prof"


class ConflictError(APIException):
    status_code = 409
    default_detail = "Conflict."
    default_code = "conflict"


def is_active_test_kit_unique_violation(error: IntegrityError) -> bool:
    return ACTIVE_TEST_KIT_UNIQUE_CONSTRAINT in str(error)


class TestKitInventoryProviderLabelSerializer(BaseModelSerializer):
    label = serializers.CharField(source="name", read_only=True)

    class Meta:
        model = Provider
        fields = ["label"]


class TestKitInventorySpecsProductSummarySerializer(BaseModelSerializer):
    label = serializers.CharField(source="test_name", read_only=True)
    product_code = serializers.CharField(source="code", read_only=True)

    class Meta:
        model = Product
        fields = ["id", "label", "product_code", "is_assignable"]


class TestKitInventorySpecsProviderSerializer(BaseModelSerializer):
    label = serializers.CharField(source="name", read_only=True)
    products = TestKitInventorySpecsProductSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Provider
        fields = ["id", "label", "products"]


class TestKitInventoryConsignmentProductWriteSerializer(BaseSerializer):
    id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(min_value=1, required=True)
    qc_ack_packaging = serializers.BooleanField(required=True)
    qc_ack_all_components = serializers.BooleanField(required=True)


class TestKitInventoryConsignmentCreateSerializer(BaseModelSerializer):
    provider = serializers.UUIDField(write_only=True)
    products = TestKitInventoryConsignmentProductWriteSerializer(
        many=True, write_only=True
    )

    class Meta:
        model = Batch
        fields = ["provider", "received_on", "products"]

    @staticmethod
    def validate_quality_checks(products_payload: list[dict]) -> list[dict]:
        for index, product_payload in enumerate(products_payload):
            if not product_payload["qc_ack_packaging"]:
                raise serializers.ValidationError(
                    {"products": {index: {"qc_ack_packaging": "This field must be true."}}}
                )
            if not product_payload["qc_ack_all_components"]:
                raise serializers.ValidationError(
                    {
                        "products": {
                            index: {
                                "qc_ack_all_components": "This field must be true."
                            }
                        }
                    }
                )
        return products_payload

    @staticmethod
    def validate_distinct_products(products_payload: list[dict]) -> list[dict]:
        product_identifiers = [str(product_payload["id"]) for product_payload in products_payload]
        if len(product_identifiers) != len(set(product_identifiers)):
            raise serializers.ValidationError(
                {"products": "Duplicate products are not allowed in a consignment."}
            )
        return products_payload

    @staticmethod
    def get_provider_or_error(provider_id) -> Provider:
        provider = Provider.objects.filter(pk=provider_id, is_active=True).first()
        if provider is None:
            raise serializers.ValidationError({"provider": "Invalid provider."})
        return provider

    @staticmethod
    def get_products_or_error(provider: Provider, products_payload: list[dict]) -> dict:
        product_identifiers = [product_payload["id"] for product_payload in products_payload]
        product_queryset = Product.objects.filter(
            pk__in=product_identifiers,
            provider=provider,
            is_active=True,
        )
        product_map = {product.pk: product for product in product_queryset}
        if len(product_map) != len(product_identifiers):
            raise serializers.ValidationError(
                {
                    "products": (
                        "All products must exist, be active, and belong to the selected provider."
                    )
                }
            )
        return product_map

    def validate(self, attrs: dict) -> dict:
        products_payload = attrs.get("products", [])
        if not products_payload:
            raise serializers.ValidationError(
                {"products": "At least one product is required."}
            )
        self.validate_quality_checks(products_payload)
        self.validate_distinct_products(products_payload)
        provider = self.get_provider_or_error(attrs["provider"])
        product_map = self.get_products_or_error(provider, products_payload)
        attrs["provider_instance"] = provider
        attrs["product_map"] = product_map
        return attrs

    def create(self, validated_data: dict) -> Batch:
        products_payload = validated_data.pop("products")
        provider = validated_data.pop("provider_instance")
        product_map = validated_data.pop("product_map")
        validated_data.pop("provider")
        batch_id = generate_test_kit_inventory_batch_id(
            provider.pk,
            provider.name,
            validated_data["received_on"],
        )
        validated_data["provider"] = provider
        validated_data["batch_id"] = batch_id
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            batch = Batch.objects.create(**validated_data)
            batch_items = self.build_batch_items(batch, product_map, products_payload)
            Item.objects.bulk_create(batch_items)

        return batch

    def build_batch_items(
        self,
        batch: Batch,
        product_map: dict,
        products_payload: list[dict],
    ) -> list[Item]:
        created_by = self.context["request"].user
        return [
            Item(
                batch=batch,
                product=product_map[product_payload["id"]],
                quantity=product_payload["quantity"],
                qc_ack_packaging=product_payload["qc_ack_packaging"],
                qc_ack_all_components=product_payload["qc_ack_all_components"],
                created_by=created_by,
            )
            for product_payload in products_payload
        ]


class TestKitInventoryAllProductSerializer(BaseModelSerializer):
    label = serializers.CharField(source="test_name", read_only=True)
    product_code = serializers.CharField(source="code", read_only=True)

    class Meta:
        model = Product
        fields = ["label", "product_code"]


class TestKitInventoryAllItemSerializer(BaseModelSerializer):
    product = serializers.SerializerMethodField()
    provider_name = serializers.CharField(source="batch.provider.name", read_only=True)
    batch_id = serializers.CharField(source="batch.batch_id", read_only=True)
    available = serializers.SerializerMethodField()
    received_on = serializers.DateField(source="batch.received_on", read_only=True)

    class Meta:
        model = Item
        fields = [
            "product",
            "provider_name",
            "batch_id",
            "quantity",
            "available",
            "received_on",
        ]

    def get_product(self, instance: Item) -> dict:
        return TestKitInventoryAllProductSerializer(
            instance.product,
            context=self.context,
        ).data

    @staticmethod
    def get_available(instance: Item) -> int:
        return instance.quantity


class TestKitInventoryBatchListSerializer(BaseModelSerializer):
    provider = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = [
            "batch_id",
            "provider",
            "products",
            "total_quantity",
            "received_on",
        ]

    def get_provider(self, instance: Batch) -> dict:
        return TestKitInventoryProviderLabelSerializer(
            instance.provider,
            context=self.context,
        ).data

    def get_products(self, instance: Batch) -> list[dict]:
        product_queryset = [batch_item.product for batch_item in instance.items.all()]
        return TestKitInventoryAllProductSerializer(
            product_queryset,
            many=True,
            context=self.context,
        ).data

    @staticmethod
    def get_total_quantity(instance: Batch) -> int:
        return sum(batch_item.quantity for batch_item in instance.items.all())


class TestKitInventoryEligibleCustomerProfileSerializer(BaseModelSerializer):
    name = serializers.SerializerMethodField()
    phone = serializers.CharField(source="customer.user.phone", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["id", "name", "phone"]

    @staticmethod
    def get_name(instance: CustomerProfile) -> str:
        return instance.get_full_name()


class TestKitInventoryAssignmentProductNameSerializer(BaseModelSerializer):
    name = serializers.CharField(source="test_name", read_only=True)

    class Meta:
        model = Product
        fields = ["name"]


class TestKitInventoryAssignmentHistorySerializer(BaseModelSerializer):
    products = TestKitInventoryAssignmentProductNameSerializer(many=True, read_only=True)
    customer = serializers.SerializerMethodField()
    clinic = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    handover_type = serializers.CharField(read_only=True)

    class Meta:
        model = Assignment
        fields = [
            "handover_type",
            "assigned_on",
            "is_kit_journey_visible",
            "products",
            "customer",
            "clinic",
            "created_by",
        ]

    @staticmethod
    def get_customer(instance: Assignment) -> dict:
        profile = instance.assigned_to
        return {
            "name": profile.get_full_name(),
            "phone": str(profile.customer.user.phone)
            if profile.customer.user.phone
            else None,
        }

    @staticmethod
    def get_clinic(instance: Assignment) -> dict | None:
        if instance.clinic is None:
            return None
        return {"name": instance.clinic.name}

    @staticmethod
    def get_created_by(instance: Assignment) -> dict | None:
        if instance.created_by is None:
            return None
        return {"name": instance.created_by.get_full_name()}


class TestKitInventoryAssignmentCreateSerializer(BaseModelSerializer):
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
        model = Assignment
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
        attrs["product_instances"] = self.get_products_or_error(attrs["products"])

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
            Product.objects.filter(
                pk__in=unique_product_ids,
                is_active=True,
                is_assignable=True,
            )
        )
        if len(products) != len(unique_product_ids):
            raise serializers.ValidationError(
                {
                    "products": (
                        "All products must exist, be active, and be assignable."
                    )
                }
            )
        return products

    def create(self, validated_data: dict) -> Assignment:
        products = validated_data.pop("product_instances")
        validated_data.pop("clinic_id", None)
        assigned_to_ids = validated_data.pop("assigned_to")
        validated_data.pop("products")

        customer_profiles = self.get_customer_profiles_or_error(assigned_to_ids)

        request = self.context["request"]
        assignment = None
        try:
            with transaction.atomic():
                for customer_profile in customer_profiles:
                    self.assert_customer_profile_eligible(customer_profile)
                    assignment = Assignment.objects.create(
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
        except IntegrityError as error:
            if not is_active_test_kit_unique_violation(error):
                raise
            raise ConflictError(
                "Customer profile already has an active test-kit assignment."
            ) from error
        return assignment


class ProviderCreateSerializer(BaseModelSerializer):
    provider_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Provider
        fields = ["id", "name", "provider_id"]
        read_only_fields = ["id"]

    @staticmethod
    def validate_provider_id(value):
        if value is None:
            return value
        catalog_provider = CatalogProvider.objects.filter(pk=value, is_active=True).first()
        if catalog_provider is None:
            raise serializers.ValidationError("Invalid provider.")
        if Provider.objects.filter(provider=catalog_provider).exists():
            raise serializers.ValidationError(
                "Provider is already linked to a test kit provider."
            )
        return value

    def create(self, validated_data: dict) -> Provider:
        provider_id = validated_data.pop("provider_id", None)
        if provider_id is not None:
            catalog_provider = CatalogProvider.objects.filter(pk=provider_id).first()
            if catalog_provider is None:
                raise serializers.ValidationError(
                    {"provider_id": "Invalid provider."}
                )
            validated_data["provider"] = catalog_provider
        return Provider.objects.create(**validated_data)


class ProductCreateSerializer(BaseModelSerializer):
    provider_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Product
        fields = ["id", "test_name", "code", "provider_id", "is_assignable"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "is_assignable": {"required": False},
        }

    @staticmethod
    def validate_provider_id(value):
        provider = Provider.objects.filter(pk=value, is_active=True).first()
        if provider is None:
            raise serializers.ValidationError("Invalid test kit provider.")
        return value

    @staticmethod
    def validate_code(value: str) -> str:
        if Product.objects.filter(code=value).exists():
            raise serializers.ValidationError(
                "Test kit product with this code already exists."
            )
        return value

    def create(self, validated_data: dict) -> Product:
        provider_id = validated_data.pop("provider_id")
        provider = Provider.objects.filter(pk=provider_id, is_active=True).first()
        if provider is None:
            raise serializers.ValidationError(
                {"provider_id": "Invalid test kit provider."}
            )
        validated_data["provider"] = provider
        return Product.objects.create(**validated_data)
