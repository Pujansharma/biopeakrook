from django.db import transaction
from rest_framework import serializers

from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer
from products.models import Product
from products.serializers import ProductIDSerializer, BaseProductSerializer
from programs.services.models import (
    Service,
    ServiceProductAssignment,
)
from programs.services.serializers import BaseServiceSerializerMeta
from programs.services.utils.constants import ServiceCategory
from programs.services.utils.db import (
    update_service_center_count,
    update_service_product_count,
)


class AssessmentServiceSerializerMeta(BaseServiceSerializerMeta):
    add_products = ProductIDSerializer(
        many=True, required=False, allow_null=True, allow_empty=True, write_only=True
    )
    remove_products = ProductIDSerializer(
        many=True, required=False, allow_null=True, allow_empty=True, write_only=True
    )
    products = serializers.SerializerMethodField(read_only=True)

    def get_products(self, instance: Service):
        product_assignments = getattr(instance, "product_assignments")
        assignment_instances = product_assignments.all()[:3]
        qs = [
            assignment_instance.product for assignment_instance in assignment_instances
        ]
        return BaseProductSerializer(qs, many=True, context=self.context).data

    @classmethod
    def get_invalid_products(cls, product_ids: list) -> set:
        existing_product_ids = set(
            Product.objects.filter(pk__in=product_ids).values_list("pk", flat=True)
        )
        return set(product_ids) - existing_product_ids

    def add_products_action(self, service: Service, add_products):
        if not add_products:
            return

        product_ids = [item.get("id") for item in add_products]
        missing_ids = self.get_invalid_products(product_ids)

        if missing_ids:
            raise serializers.ValidationError(
                {
                    "add_products": f"Invalid product IDs provided: {', '.join(map(str, missing_ids))}"
                }
            )

        products = Product.objects.filter(pk__in=product_ids)
        assignments = [
            ServiceProductAssignment(service=service, product=product, is_active=True)
            for product in products
        ]
        ServiceProductAssignment.objects.bulk_create(assignments, ignore_conflicts=True)

    def remove_products_action(self, service: Service, remove_products):
        if not remove_products:
            return

        product_ids = [item.get("id") for item in remove_products]
        missing_ids = self.get_invalid_products(product_ids)

        if missing_ids:
            raise serializers.ValidationError(
                {
                    "remove_products": f"Invalid product IDs provided: {', '.join(map(str, missing_ids))}"
                }
            )

        ServiceProductAssignment.objects.filter(
            service=service,
            product__pk__in=product_ids,
        ).delete()


class AssessmentServiceSerializer(AssessmentServiceSerializerMeta, BaseModelSerializer):
    is_active = serializers.BooleanField(default=True, required=False)
    is_locked = serializers.BooleanField(default=False, read_only=True)
    service_category_code = serializers.CharField(
        source="service_category", read_only=True
    )
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "is_global",
            "add_centers",
            "remove_centers",
            "centers",
            "centers_count",
            "service_category",
            "service_category_code",
            "image",
            "created_at",
            "updated_at",
            "is_active",
            "is_locked",
            "created_by",
            "add_products",
            "remove_products",
            "products",
            "products_count",
        ]
        read_only_fields = ["service_category"]

    def create(self, validated_data):
        is_global = validated_data.get("is_global", False)
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        if not is_global and not add_centers and not remove_centers:
            raise serializers.ValidationError("Center IDs must be provided")
        validated_data["service_category"] = ServiceCategory.ASSESSMENT
        if not is_global and not add_centers:
            raise serializers.ValidationError(
                {"add_centers": "Centers must be provided when not global."}
            )
        add_products = validated_data.pop("add_products", [])
        remove_products = validated_data.pop("remove_products", [])

        if not add_products:
            raise serializers.ValidationError(
                {"add_products": "This field is required"}
            )

        with transaction.atomic():
            service = super().create(validated_data)
            if is_global:
                self.remove_all_centers(service)
                add_centers = []
                remove_centers = []
            self.add_centers_action(service, add_centers)
            self.remove_centers_action(service, remove_centers)
            self.add_products_action(service, add_products)
            self.remove_products_action(service, remove_products)
            update_service_center_count(service.pk)
            update_service_product_count(service.pk)
        return service

    def update(self, instance: Service, validated_data):
        raise serializers.ValidationError("Update not allowed")


class AssessmentServiceDetailSerializer(
    AssessmentServiceSerializerMeta, BaseModelSerializer
):
    is_active = serializers.BooleanField(default=True, required=False)
    is_locked = serializers.BooleanField(default=False, read_only=True)
    service_category_code = serializers.CharField(
        source="service_category", read_only=True
    )
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "is_global",
            "service_category",
            "service_category_code",
            "image",
            "created_at",
            "updated_at",
            "is_active",
            "is_locked",
            "created_by",
            # Centers
            "add_centers",
            "remove_centers",
            "centers_count",
            "centers",
            # products
            "add_products",
            "remove_products",
            "products",
            "products_count",
        ]
        read_only_fields = ["service_category"]

    def create(self, validated_data):
        raise serializers.ValidationError("Create not allowed")

    def update(self, instance: Service, validated_data):
        is_global = validated_data.get("is_global", instance.is_global)
        validated_data.pop("service_category", None)
        add_centers = validated_data.pop("add_centers", [])
        remove_centers = validated_data.pop("remove_centers", [])
        add_products = validated_data.pop("add_products", [])
        remove_products = validated_data.pop("remove_products", [])

        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if is_global:
                self.remove_all_centers(service=instance)
                add_centers = []
                remove_centers = []
            self.add_centers_action(instance, add_centers)
            self.remove_centers_action(instance, remove_centers)
            self.add_products_action(instance, add_products)
            self.remove_products_action(instance, remove_products)
            update_service_product_count(instance.pk)
            instance.refresh_from_db()

            if not instance.products_count:
                raise serializers.ValidationError(
                    "No products associated with the service"
                )
            if add_centers or remove_centers or is_global:
                update_service_center_count(instance.pk)
        return instance
