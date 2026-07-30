from django.db.models import Prefetch, Q

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import BaseGenericAPIView, BaseListAPIView
from product_inventory.models import ProductInventoryBatch, ProductInventoryBatchItem
from product_inventory.serializers import (
    ProductInventoryAllItemSerializer,
    ProductInventoryBatchListSerializer,
    ProductInventoryConsignmentCreateSerializer,
    ProductInventorySpecsProviderSerializer,
)
from products.models import Product, Provider


def get_identifier_filters(
        query_params,
        query_param_name: str,
        orm_field_name: str | None = None,
) -> dict:
    filter_field_name = orm_field_name or query_param_name
    identifier_values = [
        value.strip()
        for value in query_params.getlist(query_param_name)
        if isinstance(value, str) and value.strip()
    ]
    if not identifier_values:
        return {}
    return {f"{filter_field_name}__in": identifier_values}


def get_received_on_filter(
        query_params,
        query_param_name: str = "received_on",
        orm_field_name: str | None = None,
) -> dict:
    filter_field_name = orm_field_name or query_param_name
    received_on = query_params.get(query_param_name, "").strip()
    if not received_on:
        return {}
    return {filter_field_name: received_on}


class ProductInventorySpecsView(BaseListAPIView):
    serializer_class = ProductInventorySpecsProviderSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]
    pagination_class = None

    def get_queryset(self):
        active_products = Prefetch(
            "products",
            queryset=Product.objects.filter(is_active=True).order_by("name"),
            to_attr="active_products",
        )
        return (
            Provider.objects.filter(is_active=True, products__is_active=True)
            .prefetch_related(active_products)
            .order_by("name")
            .distinct()
        )


class ProductInventoryConsignmentView(BaseGenericAPIView):
    serializer_class = ProductInventoryConsignmentCreateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = serializer.save()
        data = serializer.to_representation(batch)
        return self.send_response("Create success.", data, status=201)


class ProductInventoryAllView(BaseListAPIView):
    serializer_class = ProductInventoryAllItemSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_query = self.request.query_params.get("search_query", "").strip()
        provider_filters = get_identifier_filters(
            self.request.query_params,
            "provider",
            "batch__provider",
        )
        product_filters = get_identifier_filters(
            self.request.query_params,
            "product",
            "product",
        )
        received_on_filter = get_received_on_filter(
            self.request.query_params,
            "received_on",
            "batch__received_on",
        )
        filter_kwargs.update(provider_filters)
        filter_kwargs.update(product_filters)
        filter_kwargs.update(received_on_filter)

        if search_query:
            search |= Q(batch__batch_id__icontains=search_query)
            search |= Q(product__name__istartswith=search_query)
            search |= Q(product__name__icontains=search_query)
            search |= Q(batch__provider__name__istartswith=search_query)
            search |= Q(batch__provider__name__icontains=search_query)

        return (
            ProductInventoryBatchItem.objects.select_related(
                "batch",
                "batch__provider",
                "product",
            )
            .filter(search, **filter_kwargs)
            .order_by("-batch__received_on", "-created_at")
            .distinct()
        )


class ProductInventoryBatchesView(BaseListAPIView):
    serializer_class = ProductInventoryBatchListSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_query = self.request.query_params.get("search_query", "").strip()
        provider_filters = get_identifier_filters(
            self.request.query_params,
            "provider",
            "provider",
        )
        product_filters = get_identifier_filters(
            self.request.query_params,
            "product",
            "items__product",
        )
        received_on_filter = get_received_on_filter(
            self.request.query_params,
            "received_on",
            "received_on",
        )
        filter_kwargs.update(provider_filters)
        filter_kwargs.update(product_filters)
        filter_kwargs.update(received_on_filter)

        if search_query:
            search |= Q(batch_id__icontains=search_query)
            search |= Q(provider__name__istartswith=search_query)
            search |= Q(provider__name__icontains=search_query)
            search |= Q(items__product__name__istartswith=search_query)
            search |= Q(items__product__name__icontains=search_query)

        return (
            ProductInventoryBatch.objects.select_related("provider")
            .prefetch_related("items__product")
            .filter(search, **filter_kwargs)
            .order_by("-received_on", "-created_at")
            .distinct()
        )
