from django.db.models import Prefetch, Q

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import BaseCreateAPIView, BaseGenericAPIView, BaseListAPIView
from test_kit_inventory.models import Assignment, Batch, Item, Product, Provider
from test_kit_inventory.serializers import (
    TestKitInventoryAllItemSerializer,
    TestKitInventoryAssignmentCreateSerializer,
    TestKitInventoryAssignmentHistorySerializer,
    TestKitInventoryBatchListSerializer,
    TestKitInventoryConsignmentCreateSerializer,
    TestKitInventoryEligibleCustomerProfileSerializer,
    TestKitInventorySpecsProviderSerializer,
    ProviderCreateSerializer,
    ProductCreateSerializer,
)
from test_kit_inventory.utils.db import get_eligible_customer_profile_queryset


class TestKitInventorySpecsView(BaseListAPIView):
    serializer_class = TestKitInventorySpecsProviderSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]
    pagination_class = None

    def get_queryset(self):
        product_filter_kwargs = {"is_active": True}
        provider_filter_kwargs = {"is_active": True, "products__is_active": True}
        is_assignable_query = self.request.query_params.get("is_assignable")
        if is_assignable_query in ["0", "1"]:
            is_assignable = bool(int(is_assignable_query))
            product_filter_kwargs["is_assignable"] = is_assignable
            provider_filter_kwargs["products__is_assignable"] = is_assignable

        return (
            Provider.objects.filter(**provider_filter_kwargs)
            .prefetch_related(
                Prefetch(
                    "products",
                    queryset=Product.objects.filter(**product_filter_kwargs).order_by(
                        "test_name"
                    ),
                )
            )
            .order_by("name")
            .distinct()
        )


class TestKitInventoryConsignmentView(BaseGenericAPIView):
    serializer_class = TestKitInventoryConsignmentCreateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.send_response("Create success.", status=201)


class TestKitInventoryAllView(BaseListAPIView):
    serializer_class = TestKitInventoryAllItemSerializer
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
            search |= Q(product__test_name__istartswith=search_query)
            search |= Q(product__test_name__icontains=search_query)
            search |= Q(batch__provider__name__istartswith=search_query)
            search |= Q(batch__provider__name__icontains=search_query)

        return (
            Item.objects.select_related(
                "batch",
                "batch__provider",
                "product",
            )
            .filter(search, **filter_kwargs)
            .order_by("-batch__received_on", "-created_at")
            .distinct()
        )


class TestKitInventoryBatchesView(BaseListAPIView):
    serializer_class = TestKitInventoryBatchListSerializer
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
            search |= Q(items__product__test_name__istartswith=search_query)
            search |= Q(items__product__test_name__icontains=search_query)

        return (
            Batch.objects.select_related("provider")
            .prefetch_related("items__product")
            .filter(search, **filter_kwargs)
            .order_by("-received_on", "-created_at")
            .distinct()
        )


class TestKitInventoryEligibleCustomerListView(BaseListAPIView):
    serializer_class = TestKitInventoryEligibleCustomerProfileSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        return get_eligible_customer_profile_queryset(search)


class TestKitInventoryAssignmentCreateView(BaseCreateAPIView):
    serializer_class = TestKitInventoryAssignmentCreateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.send_response(self.get_create_success_message(), status=201)


class TestKitInventoryAssignmentHistoryListView(BaseListAPIView):
    serializer_class = TestKitInventoryAssignmentHistorySerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        queryset = (
            Assignment.objects.select_related(
                "assigned_to__customer__user",
                "clinic",
                "created_by",
            )
            .prefetch_related("products")
            .order_by("-assigned_on", "-created_at")
        )
        if not search:
            return queryset

        search_query = Q()
        search_query |= Q(assigned_to__first_name__istartswith=search)
        search_query |= Q(assigned_to__last_name__istartswith=search)
        search_query |= Q(assigned_to__first_name__icontains=search)
        search_query |= Q(assigned_to__last_name__icontains=search)
        search_query |= Q(assigned_to__customer__user__phone__icontains=search)
        search_query |= Q(clinic__name__istartswith=search)
        search_query |= Q(clinic__name__icontains=search)
        search_query |= Q(created_by__first_name__istartswith=search)
        search_query |= Q(created_by__last_name__istartswith=search)
        search_query |= Q(created_by__first_name__icontains=search)
        search_query |= Q(created_by__last_name__icontains=search)
        return queryset.filter(search_query).distinct()


class ProviderCreateView(BaseCreateAPIView):
    serializer_class = ProviderCreateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]


class ProductCreateView(BaseCreateAPIView):
    serializer_class = ProductCreateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]
