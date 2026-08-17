from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.customers.models import CustomerProfile
from core.utils.exceptions import bad_request
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from diagnostics_orders.models import (
    CatalogItem,
    DiagnosticOrder,
    DiagnosticOrderCustomer,
    DiagnosticOrderLine,
    DiagnosticOrderRescheduleHistory,
    DiagnosticsOrdersSummary,
)
from diagnostics_orders.utils.constants import (
    DiagnosticOrderStatus,
    TERMINAL_ORDER_STATUSES,
)
from diagnostics_orders.utils.db import (
    bump_summary_cancelled,
    bump_summary_orders,
    bump_summary_rescheduled,
    create_catalog_item,
    customer_profile_has_active_diagnostic_order,
    customer_profile_has_completed_pre_consultation,
    get_catalog_items,
    get_default_address,
    get_default_address_text,
    get_or_create_summary,
)
from diagnostics_orders.utils.helpers import (
    build_orange_create_payload,
    calculate_age,
    profile_gender,
    profile_label,
    sum_decimal,
    transform_serviceability_response,
    url_decode_address,
)
from integrations.orange_labs import sdk as orange_labs_sdk


class EligibleCustomerSerializer(BaseSerializer):
    name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    pincode = serializers.SerializerMethodField()

    def get_name(self, customer_profile):
        return profile_label(customer_profile)

    def get_phone(self, customer_profile):
        phone = customer_profile.customer.user.phone
        return str(phone) if phone else ""

    def get_user_id(self, customer_profile):
        return customer_profile.customer.user.pk

    def get_age(self, customer_profile):
        return calculate_age(customer_profile.date_of_birth)

    def get_gender(self, customer_profile):
        return profile_gender(customer_profile)

    def get_address(self, customer_profile):
        return get_default_address_text(customer_profile)

    def get_pincode(self, customer_profile):
        default_address = get_default_address(customer_profile)
        if default_address is None:
            return ""
        return default_address.pincode or ""


class CheckTimeslotsQuerySerializer(BaseSerializer):
    address = serializers.CharField()
    request_date = serializers.DateField()

    def validate_request_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("request_date must be today or a future date")
        return value


class CatalogItemResponseSerializer(BaseModelSerializer):
    class Meta:
        model = CatalogItem
        fields = ("test_id", "name", "price")


class AddTestPackageSerializer(BaseSerializer):
    test_id = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=255)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    def validate_test_id(self, value):
        if CatalogItem.objects.filter(test_id=value).exists():
            raise serializers.ValidationError(
                "Catalog item with this test_id already exists"
            )
        return value

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("name is required")
        return name

    def create(self, validated_data):
        return create_catalog_item(
            test_id=validated_data["test_id"],
            name=validated_data["name"],
            price=validated_data["price"],
        )


class AddTestPackageResponseSerializer(BaseModelSerializer):
    class Meta:
        model = CatalogItem
        fields = ("id", "test_id", "name", "price")


class TestPackagesQuerySerializer(BaseSerializer):
    search = serializers.CharField(required=False, allow_blank=True, default="")


class CreateOrderCustomerSerializer(BaseSerializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    gender = serializers.CharField()
    age = serializers.IntegerField(min_value=0)
    phone = serializers.CharField()
    diagnostic_tests = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_diagnostic_tests(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate test_id in diagnostic_tests")
        return value


class CreateOrderSerializer(BaseSerializer):
    address = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    slot_datetime = serializers.DateTimeField()
    customers = CreateOrderCustomerSerializer(many=True)
    idempotency_key = serializers.CharField(required=False, allow_blank=True)

    def validate_customers(self, value):
        if not value:
            raise serializers.ValidationError("At least one customer is required")
        return value

    def validate(self, attrs):
        address = url_decode_address(attrs["address"])
        attrs["address"] = address
        attrs["pincode"] = _extract_pincode_from_address(address) or ""

        requested_test_ids = {
            test_id
            for customer_data in attrs["customers"]
            for test_id in customer_data["diagnostic_tests"]
        }
        catalog_items = {
            catalog_item.test_id: catalog_item
            for catalog_item in CatalogItem.objects.filter(
                is_active=True,
                test_id__in=requested_test_ids,
            )
        }

        resolved_customers = []
        for customer_data in attrs["customers"]:
            profile = (
                CustomerProfile.objects.filter(
                    is_active=True,
                    customer__user_id=customer_data["user_id"],
                )
                .select_related("customer__user")
                .first()
            )
            if not profile:
                raise serializers.ValidationError(
                    {"customers": f"No customer profile for user_id {customer_data['user_id']}"}
                )
            if not customer_profile_has_completed_pre_consultation(profile):
                raise serializers.ValidationError(
                    {"customers": f"Pre-consultation incomplete for {customer_data['user_id']}"}
                )
            if not profile.programs.filter(is_active=True, cancelled_at__isnull=True).exists():
                raise serializers.ValidationError(
                    {"customers": f"No active program for {customer_data['user_id']}"}
                )
            if not profile.center_assignments.filter(is_active=True).exists():
                raise serializers.ValidationError(
                    {"customers": f"No center assignment for {customer_data['user_id']}"}
                )
            if customer_profile_has_active_diagnostic_order(profile):
                raise serializers.ValidationError(
                    {"customers": f"Active diagnostics order exists for {customer_data['user_id']}"}
                )

            line_snapshots = []
            for test_id in customer_data["diagnostic_tests"]:
                catalog_item = catalog_items.get(test_id)
                if catalog_item is None:
                    raise serializers.ValidationError(
                        {"customers": f"Unknown catalog item {test_id}"}
                    )
                line_snapshots.append(
                    {
                        "test_id": test_id,
                        "name": catalog_item.name,
                        "price": catalog_item.price,
                    }
                )

            resolved_customers.append(
                {
                    **customer_data,
                    "customer_profile": profile,
                    "line_snapshots": line_snapshots,
                    "customer_total": sum_decimal(
                        line["price"] for line in line_snapshots
                    ),
                }
            )

        attrs["resolved_customers"] = resolved_customers
        attrs["total_price"] = sum_decimal(
            customer["customer_total"] for customer in resolved_customers
        )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        idempotency_key = validated_data.get("idempotency_key") or None

        if idempotency_key:
            with transaction.atomic():
                get_or_create_summary()
                DiagnosticsOrdersSummary.objects.select_for_update().filter(id=1).first()
                existing = DiagnosticOrder.objects.filter(
                    idempotency_key=idempotency_key
                ).first()
                if existing:
                    return existing
                request_id, token, orange_response = self._create_orange_order(
                    validated_data
                )
                return self._persist_local_order(
                    validated_data=validated_data,
                    request=request,
                    idempotency_key=idempotency_key,
                    request_id=request_id,
                    token=token,
                    orange_response=orange_response,
                )

        request_id, token, orange_response = self._create_orange_order(validated_data)
        with transaction.atomic():
            return self._persist_local_order(
                validated_data=validated_data,
                request=request,
                idempotency_key=None,
                request_id=request_id,
                token=token,
                orange_response=orange_response,
            )

    def _create_orange_order(self, validated_data):
        orange_payload = build_orange_create_payload(
            address=validated_data["address"],
            notes=validated_data.get("notes", ""),
            slot_datetime=validated_data["slot_datetime"].strftime("%Y-%m-%dT%H:%M:%S"),
            customers=validated_data["resolved_customers"],
        )
        try:
            status_code, orange_response = orange_labs_sdk.create_order(orange_payload)
        except ValueError as exc:
            bad_request(str(exc))
        if status_code == 425:
            bad_request(
                "Duplicate booking blocked by Orange Labs. Wait 60 seconds before retrying."
            )
        if status_code >= 400:
            detail = (
                orange_response.get("detail")
                or orange_response.get("status")
                or "Orange Labs order create failed"
            )
            bad_request(str(detail))

        request_id = (
            orange_response.get("request_id")
            or (orange_response.get("data") or {}).get("request_id")
        )
        token = (
            orange_response.get("token")
            or (orange_response.get("data") or {}).get("token")
        )
        if not request_id or not token:
            bad_request("Orange Labs response missing request_id or token")
        return request_id, token, orange_response

    def _persist_local_order(
        self,
        *,
        validated_data,
        request,
        idempotency_key,
        request_id,
        token,
        orange_response,
    ):
        order = DiagnosticOrder.objects.create(
            request_id=request_id,
            token=token,
            status=DiagnosticOrderStatus.ORDER_CREATED,
            address=validated_data["address"],
            pincode=validated_data["pincode"],
            slot_datetime=validated_data["slot_datetime"],
            notes=validated_data.get("notes", ""),
            total_price=validated_data["total_price"],
            tat_in_hours=None,
            created_by=request.user if request.user.is_authenticated else None,
            idempotency_key=idempotency_key,
            raw_create_response=orange_response,
        )

        for customer in validated_data["resolved_customers"]:
            order_customer = DiagnosticOrderCustomer.objects.create(
                order=order,
                customer_profile=customer["customer_profile"],
                name=customer["name"],
                gender=customer["gender"],
                age=customer["age"],
                phone=customer["phone"],
                customer_total=customer["customer_total"],
            )
            DiagnosticOrderLine.objects.bulk_create(
                [
                    DiagnosticOrderLine(
                        order_customer=order_customer,
                        test_id=line["test_id"],
                        name=line["name"],
                        price=line["price"],
                    )
                    for line in customer["line_snapshots"]
                ]
            )

        bump_summary_orders()
        return order


class OrderListItemSerializer(BaseSerializer):
    request_id = serializers.CharField()
    customers = serializers.SerializerMethodField()
    address = serializers.CharField()
    slot_datetime = serializers.DateTimeField()
    status = serializers.CharField()
    eta = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, source="total_price")

    def get_customers(self, order):
        return [{"name": customer.name} for customer in order.customers.all()]

    def get_eta(self, order):
        if order.tat_in_hours is None:
            return None
        return order.slot_datetime + timedelta(hours=order.tat_in_hours)


class OrderLineSerializer(BaseSerializer):
    test_id = serializers.IntegerField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class OrderCustomerDetailSerializer(BaseSerializer):
    name = serializers.CharField()
    customer_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    tests = OrderLineSerializer(many=True, source="lines")


class RescheduleHistorySerializer(BaseSerializer):
    previous_slot_datetime = serializers.DateTimeField()
    new_slot_datetime = serializers.DateTimeField()
    reason = serializers.CharField()
    explanation = serializers.CharField()
    rescheduled_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()

    def get_rescheduled_by(self, history):
        if history.rescheduled_by is None:
            return None
        return history.rescheduled_by.pk


class OrderDetailSerializer(BaseSerializer):
    address = serializers.CharField()
    request_id = serializers.CharField()
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    tat_in_hours = serializers.IntegerField(allow_null=True)
    slot_datetime = serializers.DateTimeField()
    notes = serializers.CharField()
    status = serializers.CharField()
    reports = serializers.JSONField()
    customers = OrderCustomerDetailSerializer(many=True)
    reschedule_history = RescheduleHistorySerializer(many=True)


class RescheduleOrderSerializer(BaseSerializer):
    updated_slot_datetime = serializers.DateTimeField()
    reason = serializers.CharField()
    explanation = serializers.CharField()

    def validate(self, attrs):
        order = self.context["order"]
        if order.status in TERMINAL_ORDER_STATUSES:
            raise serializers.ValidationError(
                "Cannot reschedule a completed or cancelled order"
            )
        return attrs

    def save(self, **kwargs):
        order = self.context["order"]
        previous_slot_datetime = order.slot_datetime
        new_slot_datetime = self.validated_data["updated_slot_datetime"]
        reason = self.validated_data["reason"]
        explanation = self.validated_data["explanation"]
        request = self.context.get("request")
        rescheduled_by = request.user if request is not None else None
        try:
            status_code, response = orange_labs_sdk.reschedule_order(
                request_id=order.request_id,
                token=order.token,
                requested_slot_time=new_slot_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
                reason=reason,
                explanation=explanation,
            )
        except ValueError as exc:
            bad_request(str(exc))
        if status_code >= 400:
            detail = (
                response.get("detail")
                or response.get("status")
                or "Orange Labs reschedule failed"
            )
            bad_request(str(detail))

        with transaction.atomic():
            DiagnosticOrderRescheduleHistory.objects.create(
                order=order,
                previous_slot_datetime=previous_slot_datetime,
                new_slot_datetime=new_slot_datetime,
                reason=reason,
                explanation=explanation,
                rescheduled_by=rescheduled_by,
            )
            order.slot_datetime = new_slot_datetime
            order.last_reschedule_reason = reason
            order.last_reschedule_explanation = explanation
            order.save(
                update_fields=[
                    "slot_datetime",
                    "last_reschedule_reason",
                    "last_reschedule_explanation",
                    "updated_at",
                ]
            )
            bump_summary_rescheduled()
        status_value = response.get("status")
        if isinstance(status_value, dict):
            status_value = status_value.get("status")
        return {"status": status_value or order.status}


class CancelOrderSerializer(BaseSerializer):
    reason = serializers.CharField()
    explanation = serializers.CharField()

    def validate(self, attrs):
        order = self.context["order"]
        if order.status in TERMINAL_ORDER_STATUSES:
            raise serializers.ValidationError(
                "Cannot cancel a completed or cancelled order"
            )
        return attrs

    def save(self, **kwargs):
        order = self.context["order"]
        try:
            status_code, response = orange_labs_sdk.cancel_order(
                request_id=order.request_id,
                token=order.token,
                reason=self.validated_data["reason"],
                explanation=self.validated_data["explanation"],
            )
        except ValueError as exc:
            bad_request(str(exc))
        if status_code >= 400:
            detail = (
                response.get("detail")
                or response.get("status")
                or "Orange Labs cancel failed"
            )
            bad_request(str(detail))

        order.status = DiagnosticOrderStatus.ORDER_CANCELLED
        order.cancelled_at = timezone.now()
        order.cancel_reason = self.validated_data["reason"]
        order.cancel_explanation = self.validated_data["explanation"]
        order.save(
            update_fields=[
                "status",
                "cancelled_at",
                "cancel_reason",
                "cancel_explanation",
                "updated_at",
            ]
        )
        bump_summary_cancelled()
        status_value = response.get("status")
        if isinstance(status_value, dict):
            status_value = status_value.get("status")
        return {"status": status_value or order.status}


def build_test_packages_payload(search=""):
    items = get_catalog_items(search=search)
    return {"tests": CatalogItemResponseSerializer(items, many=True).data}


def build_timeslots_payload(address, request_date):
    try:
        status_code, response = orange_labs_sdk.check_serviceability(
            address=address,
            request_date=request_date.isoformat(),
        )
    except ValueError as exc:
        bad_request(str(exc))
    return transform_serviceability_response(response, status_code)


def _extract_pincode_from_address(address):
    tokens = [token.strip(" ,") for token in str(address).replace(",", " ").split()]
    for token in reversed(tokens):
        if token.isdigit() and len(token) == 6:
            return token
    return None
