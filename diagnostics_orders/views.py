from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from accounts.utils.permissions import DiagnosticsOrdersFeaturePermission, IsAdminUser
from core.utils.views.main import BaseGenericAPIView, BaseListAPIView
from diagnostics_orders.models import DiagnosticOrder
from diagnostics_orders.serializers import (
    AddTestPackageResponseSerializer,
    AddTestPackageSerializer,
    CancelOrderSerializer,
    CheckTimeslotsQuerySerializer,
    CreateOrderSerializer,
    EligibleCustomerSerializer,
    OrderDetailSerializer,
    OrderListItemSerializer,
    RescheduleOrderSerializer,
    TestPackagesQuerySerializer,
    build_test_packages_payload,
    build_timeslots_payload,
)
from diagnostics_orders.utils.constants import CollectionDateFilter
from diagnostics_orders.utils.db import (
    get_eligible_customer_profile_queryset,
    get_order_by_request_id,
    get_orders_queryset,
    serialize_eligible_customer,
)
from diagnostics_orders.utils.helpers import resolve_city_from_pincode


class EligibleCustomersListView(BaseListAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = EligibleCustomerSerializer

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        center = self.request.query_params.get("center")
        return get_eligible_customer_profile_queryset(search=search, center_id=center)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        profiles = page if page is not None else list(queryset)
        data = [serialize_eligible_customer(profile) for profile in profiles]
        serializer = self.get_serializer(data, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class CheckTimeslotsView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = CheckTimeslotsQuerySerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = build_timeslots_payload(
            address=serializer.validated_data["address"],
            request_date=serializer.validated_data["request_date"],
        )
        return self.send_response("Timeslots fetched.", data=data)


class TestPackagesListView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = TestPackagesQuerySerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        city = resolve_city_from_pincode(serializer.validated_data["pincode"])
        if not city:
            self.raise_bad_request("Unsupported or invalid pincode")
        data = build_test_packages_payload(
            city=city,
            search=serializer.validated_data.get("search", ""),
        )
        return self.send_response("Catalog fetched.", data=data)


class AddTestPackageView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = AddTestPackageSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        catalog_item = serializer.save()
        response_data = AddTestPackageResponseSerializer(catalog_item).data
        return self.send_response(
            "Catalog item created.",
            data=response_data,
            status=201,
        )


class CreateOrderView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = CreateOrderSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return self.send_response(
            "Order created.",
            data={"request_id": order.request_id},
            status=201,
        )


class OrdersListView(BaseListAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = OrderListItemSerializer

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        status = self.request.query_params.get("status")
        cities = self.request.query_params.getlist("cities")
        collection_date = self.request.query_params.get(
            "collection_date", CollectionDateFilter.ALL
        )
        if collection_date not in CollectionDateFilter.CHOICES:
            collection_date = CollectionDateFilter.ALL
        return get_orders_queryset(
            search=search,
            status=status,
            cities=cities or None,
            collection_date=collection_date,
        )


class OrderDetailView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = OrderDetailSerializer

    def get(self, request, request_id, *args, **kwargs):
        order = _get_order_or_404(request_id)
        serializer = self.get_serializer(order)
        return self.send_response("Order detail.", data=serializer.data)


class RescheduleOrderView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = RescheduleOrderSerializer

    def patch(self, request, request_id, *args, **kwargs):
        order = _get_order_or_404(request_id)
        context = {**self.get_serializer_context(), "order": order}
        serializer = self.get_serializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return self.send_response("Order rescheduled.", data=data)


class CancelOrderView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | DiagnosticsOrdersFeaturePermission]
    serializer_class = CancelOrderSerializer

    def patch(self, request, request_id, *args, **kwargs):
        order = _get_order_or_404(request_id)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return self.send_response("Order cancelled.", data=data)


def _get_order_or_404(request_id):
    try:
        return get_order_by_request_id(request_id)
    except DiagnosticOrder.DoesNotExist as exc:
        raise NotFound("Order not found") from exc
