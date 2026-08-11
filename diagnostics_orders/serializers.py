from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.customers.models import CustomerProfile
from core.utils.exceptions import bad_request
from core.utils.serializers import BaseSerializer
from diagnostics_orders.models import (
    CatalogItem,
    DiagnosticOrder,
    DiagnosticOrderCustomer,
    DiagnosticOrderLine,
)
from diagnostics_orders.utils.constants import (
    CatalogCategory,
    DiagnosticOrderStatus,
)
from diagnostics_orders.utils.db import (
    bump_summary_cancelled,
    bump_summary_orders,
    bump_summary_rescheduled,
    customer_profile_has_active_diagnostic_order,
    customer_profile_has_completed_pre_consultation,
    get_catalog_items_for_city,
)
from diagnostics_orders.utils.helpers import (
    build_orange_create_payload,
    max_tat_hours,
    resolve_city_from_pincode,
    sum_decimal,
    transform_serviceability_response,
    url_decode_address,
    url_encode_address,
)
from integrations.orange_labs import sdk as orange_labs_sdk


class EligibleCustomerSerializer(BaseSerializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    user_id = serializers.UUIDField()
    age = serializers.IntegerField(allow_null=True)
    gender = serializers.CharField(allow_null=True)
    address = serializers.CharField()


class CheckTimeslotsQuerySerializer(BaseSerializer):
    address = serializers.CharField()
    request_date = serializers.DateField()

    def validate_request_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("request_date must be today or a future date")
        return value


class CatalogItemResponseSerializer(BaseSerializer):
    id = serializers.CharField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    fasting_required = serializers.BooleanField()


class TestPackagesQuerySerializer(BaseSerializer):
    pincode = serializers.CharField()
    search = serializers.CharField(required=False, allow_blank=True, default="")


class DiagnosticTestInputSerializer(BaseSerializer):
    diagnostic_test_id = serializers.CharField()
    category = serializers.ChoiceField(choices=CatalogCategory.choices)


class CreateOrderCustomerSerializer(BaseSerializer):
    user_id = serializers.UUIDField()
    name = serializers.CharField()
    gender = serializers.CharField()
    age = serializers.IntegerField(min_value=0)
    phone = serializers.CharField()
    diagnostic_tests = DiagnosticTestInputSerializer(many=True)

    def validate_diagnostic_tests(self, value):
        if not value:
            raise serializers.ValidationError("At least one diagnostic test is required")
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
        pincode = _extract_pincode_from_address(address)
        city = resolve_city_from_pincode(pincode) if pincode else None
        if not city:
            raise serializers.ValidationError(
                {"address": "Unable to resolve city from address pincode"}
            )
        attrs["pincode"] = pincode
        attrs["city"] = city

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
            for item in customer_data["diagnostic_tests"]:
                catalog_item = (
                    CatalogItem.objects.filter(
                        is_active=True,
                        diagnostic_test_id=item["diagnostic_test_id"],
                        category=item["category"],
                    )
                    .prefetch_related("city_prices")
                    .first()
                )
                if not catalog_item:
                    raise serializers.ValidationError(
                        {
                            "customers": (
                                f"Unknown catalog item {item['diagnostic_test_id']}"
                            )
                        }
                    )
                city_price = catalog_item.city_prices.filter(
                    city=city, is_active=True
                ).first()
                if not city_price:
                    raise serializers.ValidationError(
                        {
                            "customers": (
                                f"No price for {item['diagnostic_test_id']} in {city}"
                            )
                        }
                    )
                line_snapshots.append(
                    {
                        "category": item["category"],
                        "diagnostic_test_id": item["diagnostic_test_id"],
                        "name": catalog_item.name,
                        "price": city_price.price,
                        "tat_in_hours": city_price.tat_in_hours,
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
        attrs["tat_in_hours"] = max_tat_hours(
            line["tat_in_hours"]
            for customer in resolved_customers
            for line in customer["line_snapshots"]
        )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        idempotency_key = validated_data.get("idempotency_key") or None
        if idempotency_key:
            existing = DiagnosticOrder.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            if existing:
                return existing

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

        order = DiagnosticOrder.objects.create(
            request_id=request_id,
            token=token,
            status=DiagnosticOrderStatus.ORDER_CREATED,
            address=validated_data["address"],
            city=validated_data["city"],
            pincode=validated_data["pincode"],
            slot_datetime=validated_data["slot_datetime"],
            notes=validated_data.get("notes", ""),
            total_price=validated_data["total_price"],
            tat_in_hours=validated_data["tat_in_hours"],
            created_by=request.user if request.user.is_authenticated else None,
            idempotency_key=idempotency_key,
            raw_create_request=orange_payload,
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
                        category=line["category"],
                        diagnostic_test_id=line["diagnostic_test_id"],
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
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class OrderCustomerDetailSerializer(BaseSerializer):
    name = serializers.CharField()
    customer_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    tests = serializers.SerializerMethodField()
    packages = serializers.SerializerMethodField()

    def get_tests(self, order_customer):
        lines = [
            line
            for line in order_customer.lines.all()
            if line.category == CatalogCategory.TEST
        ]
        return OrderLineSerializer(lines, many=True).data

    def get_packages(self, order_customer):
        lines = [
            line
            for line in order_customer.lines.all()
            if line.category == CatalogCategory.PACKAGE
        ]
        return OrderLineSerializer(lines, many=True).data


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


class RescheduleOrderSerializer(BaseSerializer):
    updated_slot_datetime = serializers.DateTimeField()
    reason = serializers.CharField()
    explanation = serializers.CharField()

    def save(self, **kwargs):
        order = self.context["order"]
        try:
            status_code, response = orange_labs_sdk.reschedule_order(
                request_id=order.request_id,
                token=order.token,
                requested_slot_time=self.validated_data["updated_slot_datetime"].strftime(
                    "%Y-%m-%dT%H:%M:%S"
                ),
                reason=self.validated_data["reason"],
                explanation=self.validated_data["explanation"],
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

        order.slot_datetime = self.validated_data["updated_slot_datetime"]
        order.last_reschedule_reason = self.validated_data["reason"]
        order.last_reschedule_explanation = self.validated_data["explanation"]
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


def build_test_packages_payload(city, search=""):
    items = get_catalog_items_for_city(city, search=search)
    tests = []
    packages = []
    custom_packages = []
    for item in items:
        matched = getattr(item, "matched_city_prices", None) or []
        if not matched:
            continue
        city_price = matched[0]
        payload = {
            "id": item.diagnostic_test_id,
            "name": item.name,
            "price": city_price.price,
            "fasting_required": item.fasting_required,
        }
        if item.category == CatalogCategory.TEST:
            tests.append(payload)
        elif item.is_custom_package:
            custom_packages.append(payload)
        else:
            packages.append(payload)
    return {
        "tests": tests,
        "packages": packages,
        "custom_packages": custom_packages,
    }


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
