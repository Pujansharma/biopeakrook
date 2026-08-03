from django.db import transaction
from rest_framework import serializers

from core.utils.serializers import BaseModelSerializer, BaseSerializer
from product_inventory.models import ProductInventoryBatch, ProductInventoryBatchItem
from product_inventory.utils import (
    generate_product_inventory_batch_id,
    get_product_inventory_code,
)
from products.models import Product, Provider


class ProductInventoryProviderLabelSerializer(BaseModelSerializer):
    label = serializers.CharField(source="name", read_only=True)

    class Meta:
        model = Provider
        fields = ["label"]


class ProductInventoryProductSummarySerializer(BaseModelSerializer):
    label = serializers.CharField(source="name", read_only=True)
    product_code = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "label", "product_code"]

    @staticmethod
    def get_product_code(instance: Product) -> str:
        return get_product_inventory_code(instance.name)


class ProductInventorySpecsProviderSerializer(BaseModelSerializer):
    label = serializers.CharField(source="name", read_only=True)
    products = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = ["id", "label", "products"]

    def get_products(self, instance: Provider) -> list[dict]:
        product_queryset = getattr(instance, "active_products", None)
        if product_queryset is None:
            product_queryset = instance.products.filter(is_active=True)
        return ProductInventoryProductSummarySerializer(
            product_queryset,
            many=True,
            context=self.context,
        ).data


class ProductInventoryConsignmentProductWriteSerializer(BaseSerializer):
    id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(min_value=1, required=True)
    qc_ack_packaging = serializers.BooleanField(required=True)
    qc_ack_all_components = serializers.BooleanField(required=True)


class ProductInventoryConsignmentCreateSerializer(BaseModelSerializer):
    provider = serializers.UUIDField(write_only=True)
    products = ProductInventoryConsignmentProductWriteSerializer(
        many=True, write_only=True
    )

    class Meta:
        model = ProductInventoryBatch
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
        product_map = {product.id: product for product in product_queryset}
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

    def create(self, validated_data: dict) -> ProductInventoryBatch:
        products_payload = validated_data.pop("products")
        provider = validated_data.pop("provider_instance")
        product_map = validated_data.pop("product_map")
        validated_data.pop("provider")
        batch_id = generate_product_inventory_batch_id(
            provider.id,
            provider.name,
            validated_data["received_on"],
        )
        validated_data["provider"] = provider
        validated_data["batch_id"] = batch_id
        validated_data["created_by"] = self.context["request"].user

        with transaction.atomic():
            batch = ProductInventoryBatch.objects.create(**validated_data)
            batch_items = self.build_batch_items(batch, product_map, products_payload)
            ProductInventoryBatchItem.objects.bulk_create(batch_items)

        return (
            ProductInventoryBatch.objects.select_related("provider")
            .prefetch_related("items__product")
            .filter(pk=batch.pk)
            .first()
        )

    def build_batch_items(
        self,
        batch: ProductInventoryBatch,
        product_map: dict,
        products_payload: list[dict],
    ) -> list[ProductInventoryBatchItem]:
        created_by = self.context["request"].user
        return [
            ProductInventoryBatchItem(
                batch=batch,
                product=product_map[product_payload["id"]],
                quantity=product_payload["quantity"],
                qc_ack_packaging=product_payload["qc_ack_packaging"],
                qc_ack_all_components=product_payload["qc_ack_all_components"],
                created_by=created_by,
            )
            for product_payload in products_payload
        ]

    def to_representation(self, instance: ProductInventoryBatch) -> list[dict]:
        item_queryset = instance.items.select_related("product", "batch__provider").all()
        return ProductInventoryConsignmentResponseItemSerializer(
            item_queryset,
            many=True,
            context=self.context,
        ).data


class ProductInventoryConsignmentResponseItemSerializer(BaseModelSerializer):
    product_code = serializers.SerializerMethodField()
    label = serializers.CharField(source="product.name", read_only=True)
    available = serializers.SerializerMethodField()
    received_on = serializers.DateField(source="batch.received_on", read_only=True)
    batch_id = serializers.CharField(source="batch.batch_id", read_only=True)
    provider = serializers.SerializerMethodField()

    class Meta:
        model = ProductInventoryBatchItem
        fields = [
            "product_code",
            "label",
            "quantity",
            "available",
            "received_on",
            "batch_id",
            "provider",
        ]

    @staticmethod
    def get_product_code(instance: ProductInventoryBatchItem) -> str:
        return get_product_inventory_code(instance.product.name)

    @staticmethod
    def get_available(instance: ProductInventoryBatchItem) -> int:
        return instance.quantity

    def get_provider(self, instance: ProductInventoryBatchItem) -> dict:
        return ProductInventoryProviderLabelSerializer(
            instance.batch.provider,
            context=self.context,
        ).data


class ProductInventoryAllProductSerializer(BaseModelSerializer):
    label = serializers.CharField(source="name", read_only=True)
    product_code = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["label", "product_code"]

    @staticmethod
    def get_product_code(instance: Product) -> str:
        return get_product_inventory_code(instance.name)


class ProductInventoryAllItemSerializer(BaseModelSerializer):
    product = serializers.SerializerMethodField()
    provider_name = serializers.CharField(source="batch.provider.name", read_only=True)
    batch_id = serializers.CharField(source="batch.batch_id", read_only=True)
    available = serializers.SerializerMethodField()
    received_on = serializers.DateField(source="batch.received_on", read_only=True)

    class Meta:
        model = ProductInventoryBatchItem
        fields = [
            "product",
            "provider_name",
            "batch_id",
            "quantity",
            "available",
            "received_on",
        ]

    def get_product(self, instance: ProductInventoryBatchItem) -> dict:
        return ProductInventoryAllProductSerializer(
            instance.product,
            context=self.context,
        ).data

    @staticmethod
    def get_available(instance: ProductInventoryBatchItem) -> int:
        return instance.quantity


class ProductInventoryBatchListSerializer(BaseModelSerializer):
    provider = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()
    total_quantity = serializers.SerializerMethodField()

    class Meta:
        model = ProductInventoryBatch
        fields = [
            "batch_id",
            "provider",
            "products",
            "total_quantity",
            "received_on",
        ]

    def get_provider(self, instance: ProductInventoryBatch) -> dict:
        return ProductInventoryProviderLabelSerializer(
            instance.provider,
            context=self.context,
        ).data

    def get_products(self, instance: ProductInventoryBatch) -> list[dict]:
        product_queryset = [batch_item.product for batch_item in instance.items.all()]
        return ProductInventoryAllProductSerializer(
            product_queryset,
            many=True,
            context=self.context,
        ).data

    @staticmethod
    def get_total_quantity(instance: ProductInventoryBatch) -> int:
        return sum(batch_item.quantity for batch_item in instance.items.all())
