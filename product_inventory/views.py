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
        serializer.save()
        return self.send_response("Create success.", serializer.data, status=201)


class ProductInventoryAllView(BaseListAPIView):
    serializer_class = ProductInventoryAllItemSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_query = self.request.query_params.get("search", "").strip()
        provider_ids = self.request.query_params.getlist("provider")
        product_ids = self.request.query_params.getlist("product")
        received_on = self.request.query_params.get("received_on", "").strip()

        if provider_ids:
            filter_kwargs["batch__provider__in"] = provider_ids
        if product_ids:
            filter_kwargs["product__in"] = product_ids
        if received_on:
            filter_kwargs["batch__received_on"] = received_on

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
        search_query = self.request.query_params.get("search", "").strip()
        provider_ids = self.request.query_params.getlist("provider")
        product_ids = self.request.query_params.getlist("product")
        received_on = self.request.query_params.get("received_on", "").strip()

        if provider_ids:
            filter_kwargs["provider__in"] = provider_ids
        if product_ids:
            filter_kwargs["items__product__in"] = product_ids
        if received_on:
            filter_kwargs["received_on"] = received_on

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
