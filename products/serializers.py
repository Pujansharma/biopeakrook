from django.db import transaction
from rest_framework import serializers

from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from products.models import Product, Provider, ProviderAPI
from products.utils.constants import PROVIDER_PRODUCT_CALLBACK_MAP, FetchProfileFieldChoices
from products.utils.db import update_provider_products_count
from products.utils.helper import generate_product_code, generate_provider_code


class ProductIDSerializer(BaseSerializer):
    id = serializers.UUIDField(required=True)


class BaseProductSerializer(BaseModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "code"]


class BaseProviderSerializer(BaseModelSerializer):
    class Meta:
        model = Provider
        fields = ["id", "name", "code"]


class ProductSerializer(BaseModelSerializer):
    provider = BaseProviderSerializer(read_only=True)
    provider_id = serializers.UUIDField(write_only=True)
    is_active = serializers.BooleanField(default=True, required=False)
    created_by = BaseUserSerializer(read_only=True)
    callback_code = serializers.CharField(source="callback", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "provider",
            "provider_id",
            "name",
            "callback",
            "callback_code",
            "code",
            "is_active",
            "data",
            "tags",
            "sample_file",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]

    def create(self, validated_data: dict) -> Product:
        provider_id = validated_data.get("provider_id")
        callback = validated_data.get("callback")
        provider = Provider.objects.filter(pk=provider_id).first()
        if not provider:
            raise serializers.ValidationError({"provider_id": "Invalid provider ID."})

        if callback not in PROVIDER_PRODUCT_CALLBACK_MAP[provider.callback]:
            raise serializers.ValidationError(
                {"callback": "Invalid callback selected for the given provider"}
            )

        validated_data["code"] = generate_product_code()
        with transaction.atomic():
            product = super().create(validated_data)
            update_provider_products_count(product.provider.pk)
        return product

    def update(self, instance: Product, validated_data: dict) -> Product:
        validated_data.pop("code", None)
        validated_data.pop("provider_id", None)
        validated_data.pop("callback", None)
        return super().update(instance, validated_data)


class MinimumProviderSerializer(BaseModelSerializer):
    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "code",
            "image",
            "is_active",
            "is_api_enabled",
            "created_at",
            "updated_at",
        ]


class ProviderSerializer(BaseModelSerializer):
    has_api = serializers.BooleanField(default=False, read_only=True)
    is_active = serializers.BooleanField(default=True, required=False)
    callback_code = serializers.CharField(source="callback", read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    products = serializers.SerializerMethodField(read_only=True)
    required_fields = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_empty=True,
        allow_null=True,
    )
    fetch_fields = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_empty=True,
        allow_null=True,
    )
    fetch_profile_fields = serializers.MultipleChoiceField(
        choices=list(FetchProfileFieldChoices.values),
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "callback",
            "callback_code",
            "code",
            "image",
            "website",
            "contact_first_name",
            "contact_last_name",
            "contact_email",
            "contact_phone",
            "required_fields",
            "fetch_fields",
            "fetch_profile_fields",
            "has_api",
            "is_active",
            "is_api_enabled",
            "products_count",
            "created_at",
            "updated_at",
            "created_by",
            "products",
        ]
        read_only_fields = ["id", "code", "created_at", "updated_at"]

    def get_products(self, instance):
        _products = getattr(instance, "products", None)
        if not _products:
            return None
        qs = _products.all()[:3]
        return BaseProductSerializer(qs, many=True, context=self.context).data

    def validate(self, attrs):
        _required_fields = attrs.pop("required_fields") or []
        _fetch_fields = attrs.pop("fetch_fields") or []

        required_fields = list(filter(None, _required_fields))
        fetch_fields = list(filter(None, _fetch_fields))

        attrs["required_fields"] = required_fields
        attrs["fetch_fields"] = fetch_fields
        return attrs

    def create(self, validated_data: dict) -> Provider:
        validated_data["code"] = generate_provider_code()
        return super().create(validated_data)

    def update(self, instance: Provider, validated_data: dict) -> Provider:
        validated_data.pop("code", None)
        required_fields = validated_data.get("required_fields") or []
        if instance.is_api_enabled:
            api_instance = getattr(instance, "api", None)
            _data: dict = getattr(api_instance, "data", {}) or {}

            is_configured = bool(required_fields) and all(
                [_data.get(x) for x in required_fields]
            )
            validated_data["is_api_enabled"] = is_configured and validated_data.get(
                "is_api_enabled", instance.is_api_enabled
            )

        return super().update(instance, validated_data)


class ProviderAPISerializer(BaseModelSerializer):
    is_active = serializers.BooleanField(default=True)
    is_api_enabled = serializers.BooleanField(source="provider.is_api_enabled")

    class Meta:
        model = ProviderAPI
        fields = ["data", "is_api_enabled", "is_active"]

    @classmethod
    def validate_required_fields(cls, required_fields: list, data: dict) -> dict:
        errors = {}
        for key in required_fields:
            if key not in data:
                errors[key] = (
                    "This field is needed as it is mentioned in required fields."
                )
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        _provider = validated_data.pop("_provider")
        provider_data = validated_data.pop("provider", {})
        required_fields = _provider.required_fields
        if not required_fields:
            raise serializers.ValidationError(
                "Provider does not have required fields, cannot add API."
            )
        _data = validated_data.get("data") or {}
        data = self.validate_required_fields(required_fields, _data)
        validated_data["data"] = data
        validated_data["provider"] = _provider
        with transaction.atomic():
            for key, value in provider_data.items():
                setattr(_provider, key, value)
            instance = super().create(validated_data)
            _provider.save(update_fields=[*provider_data.keys(), "updated_at"])
        return instance

    def update(self, instance: ProviderAPI, validated_data: dict) -> ProviderAPI:
        required_fields = instance.provider.required_fields
        provider_data = validated_data.pop("provider", {})
        is_api_enabled = provider_data.get(
            "is_api_enabled", instance.provider.is_api_enabled
        )
        if is_api_enabled:
            if not required_fields:
                raise serializers.ValidationError(
                    "Provider does not have required fields, cannot update API."
                )

            _data = validated_data.get("data", instance.data) or {}
            validated_data["data"] = self.validate_required_fields(
                required_fields, _data
            )
        with transaction.atomic():
            for key, value in provider_data.items():
                setattr(instance.provider, key, value)
            instance.provider.save(update_fields=[*provider_data.keys(), "updated_at"])
            instance = super().update(instance, validated_data)
        return instance


class ServiceAvailableProductSerializer(BaseModelSerializer):
    exists = serializers.BooleanField(default=False)
    provider = BaseProviderSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "image",
            "name",
            "provider",
            "exists",
        ]


class AssessmentServiceProviderSerializer(BaseModelSerializer):
    fetch_fields = serializers.SerializerMethodField()
    fetch_profile_fields = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = [
            "id",
            "name",
            "code",
            "is_api_enabled",
            "fetch_fields",
            "fetch_profile_fields",
        ]

    def get_fetch_fields(self, instance):
        return instance.fetch_fields or []

    def get_fetch_profile_fields(self, instance):
        return instance.fetch_profile_fields or []
