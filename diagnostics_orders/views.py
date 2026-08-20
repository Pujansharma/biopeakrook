from datetime import timedelta

from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework.exceptions import NotFound

from accounts.customers.models import CustomerProfile
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import BaseGenericAPIView, BaseListAPIView
from diagnostics_orders.models import (
    CatalogItem,
    DiagnosticOrder,
    DiagnosticOrderCustomer,
    DiagnosticOrderLine,
    DiagnosticOrderRescheduleHistory,
)
from diagnostics_orders.serializers import (
    AddTestPackageResponseSerializer,
    AddTestPackageSerializer,
    CancelOrderSerializer,
    CatalogItemResponseSerializer,
    CheckTimeslotsQuerySerializer,
    CreateOrderSerializer,
    EligibleCustomerSerializer,
    OrderDetailSerializer,
    OrderListItemSerializer,
    RescheduleOrderSerializer,
    TestPackagesQuerySerializer,
    build_timeslots_payload,
)
from diagnostics_orders.utils.constants import (
    CollectionDateFilter,
    TERMINAL_ORDER_STATUSES,
)


class EligibleCustomersViewMeta(BaseGenericAPIView):
    def get_eligible_customer_profile_queryset(self):
        filter_kwargs = {}
        search = self.request.query_params.get("search", "").strip()
        center_id = self.request.query_params.get("center")
        if center_id:
            filter_kwargs["center_assignments__center_id"] = center_id

        active_order_profile_ids = (
            DiagnosticOrderCustomer.objects.filter(order__is_active=True)
            .exclude(order__status__in=TERMINAL_ORDER_STATUSES)
            .values_list("customer_profile_id", flat=True)
        )

        queryset = (
            CustomerProfile.objects.filter(
                is_active=True,
                is_onboarding_completed=True,
                center_assignments__is_active=True,
                **filter_kwargs,
            )
            .exclude(id__in=active_order_profile_ids)
            .select_related("customer__user")
            .prefetch_related("addresses")
            .order_by("-created_at")
            .distinct()
        )

        if not search:
            return queryset

        search_query = Q()
        search_query |= Q(first_name__istartswith=search)
        search_query |= Q(last_name__istartswith=search)
        search_query |= Q(first_name__icontains=search)
        search_query |= Q(last_name__icontains=search)
        search_query |= Q(customer__user__phone__icontains=search)
        return queryset.filter(search_query)


class EligibleCustomersListView(EligibleCustomersViewMeta, BaseListAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = EligibleCustomerSerializer

    def get_queryset(self):
        return self.get_eligible_customer_profile_queryset()


class CheckTimeslotsView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
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
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = TestPackagesQuerySerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        search = serializer.validated_data.get("search", "").strip()
        queryset = CatalogItem.objects.filter(is_active=True).order_by("name")
        if search:
            queryset = queryset.filter(name__icontains=search)
        data = {
            "tests": CatalogItemResponseSerializer(queryset, many=True).data,
        }
        return self.send_response("Catalog fetched.", data=data)


class AddTestPackageView(BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
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
    permission_classes = [IsAdminUser | IsAssociateUser]
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


class OrdersListViewMeta(BaseGenericAPIView):
    def get_orders_queryset(self):
        filter_kwargs = {}
        search = self.request.query_params.get("search", "").strip()
        status = self.request.query_params.get("status")
        collection_date = self.request.query_params.get(
            "collection_date", CollectionDateFilter.ALL
        )
        if collection_date not in CollectionDateFilter.CHOICES:
            collection_date = CollectionDateFilter.ALL

        if status:
            filter_kwargs["status"] = status

        queryset = (
            DiagnosticOrder.objects.filter(is_active=True, **filter_kwargs)
            .prefetch_related("customers")
            .order_by("-created_at")
        )

        if search:
            search_query = Q(request_id__icontains=search)
            search_query |= Q(address__icontains=search)
            search_query |= Q(customers__name__icontains=search)
            queryset = queryset.filter(search_query).distinct()

        if collection_date != CollectionDateFilter.ALL:
            now = timezone.localdate()
            if collection_date == CollectionDateFilter.TODAY:
                queryset = queryset.filter(slot_datetime__date=now)
            elif collection_date == CollectionDateFilter.TOMORROW:
                queryset = queryset.filter(
                    slot_datetime__date=now + timedelta(days=1)
                )
            elif collection_date == CollectionDateFilter.PAST_7_DAYS:
                queryset = queryset.filter(
                    slot_datetime__date__gte=now - timedelta(days=7),
                    slot_datetime__date__lte=now,
                )
            elif collection_date == CollectionDateFilter.UPCOMING:
                queryset = queryset.filter(slot_datetime__date__gt=now)
        return queryset


class OrdersListView(OrdersListViewMeta, BaseListAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = OrderListItemSerializer

    def get_queryset(self):
        return self.get_orders_queryset()


class DiagnosticOrderViewMeta(BaseGenericAPIView):
    def get_order_detail_queryset(self):
        return DiagnosticOrder.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "customers",
                queryset=DiagnosticOrderCustomer.objects.prefetch_related(
                    Prefetch(
                        "lines",
                        queryset=DiagnosticOrderLine.objects.all(),
                    )
                ),
            ),
            Prefetch(
                "reschedule_history",
                queryset=DiagnosticOrderRescheduleHistory.objects.select_related(
                    "rescheduled_by"
                ),
            ),
        )

    def get_order_or_404(self, request_id):
        order = self.get_order_detail_queryset().filter(request_id=request_id).first()
        if order is None:
            raise NotFound("Order not found")
        return order


class OrderDetailView(DiagnosticOrderViewMeta, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = OrderDetailSerializer

    def get(self, request, request_id, *args, **kwargs):
        order = self.get_order_or_404(request_id)
        serializer = self.get_serializer(order)
        return self.send_response("Order detail.", data=serializer.data)


class RescheduleOrderView(DiagnosticOrderViewMeta, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = RescheduleOrderSerializer

    def patch(self, request, request_id, *args, **kwargs):
        order = self.get_order_or_404(request_id)
        context = {**self.get_serializer_context(), "order": order}
        serializer = self.get_serializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return self.send_response("Order rescheduled.", data=data)


class CancelOrderView(DiagnosticOrderViewMeta, BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CancelOrderSerializer

    def patch(self, request, request_id, *args, **kwargs):
        order = self.get_order_or_404(request_id)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return self.send_response("Order cancelled.", data=data)
