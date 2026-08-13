from django.db import transaction
from django.db.models import F, Prefetch

from diagnostics_orders.models import (
    CatalogCityPrice,
    CatalogItem,
    DiagnosticOrderCustomer,
    DiagnosticsOrdersSummary,
)
from diagnostics_orders.utils.constants import TERMINAL_ORDER_STATUSES
from diagnostics_orders.utils.helpers import calculate_age, profile_gender, profile_label
from pre_consultation.models import PreConsultationSession
from pre_consultation.utils.constants import PreConsultationSessionStatus


def get_or_create_summary():
    summary, _ = DiagnosticsOrdersSummary.objects.get_or_create(id=1)
    return summary


def bump_summary_orders():
    get_or_create_summary()
    DiagnosticsOrdersSummary.objects.filter(id=1).update(
        total_orders=F("total_orders") + 1
    )


def bump_summary_rescheduled():
    get_or_create_summary()
    DiagnosticsOrdersSummary.objects.filter(id=1).update(
        total_rescheduled=F("total_rescheduled") + 1
    )


def bump_summary_cancelled():
    get_or_create_summary()
    DiagnosticsOrdersSummary.objects.filter(id=1).update(
        total_cancelled=F("total_cancelled") + 1
    )


def bump_summary_completed():
    get_or_create_summary()
    DiagnosticsOrdersSummary.objects.filter(id=1).update(
        total_completed=F("total_completed") + 1
    )


def customer_profile_has_completed_pre_consultation(customer_profile):
    return PreConsultationSession.objects.filter(
        user_id=customer_profile.customer.user_id,
        status=PreConsultationSessionStatus.COMPLETED,
    ).exists()


def customer_profile_has_active_diagnostic_order(customer_profile):
    return (
        DiagnosticOrderCustomer.objects.filter(
            customer_profile=customer_profile,
            order__is_active=True,
        )
        .exclude(order__status__in=TERMINAL_ORDER_STATUSES)
        .exists()
    )


def get_default_address(customer_profile):
    addresses = list(customer_profile.addresses.all())
    if not addresses:
        return None
    default_address = None
    for address in addresses:
        if address.is_default and address.is_active:
            default_address = address
            break
    if default_address is None:
        for address in addresses:
            if address.is_active:
                default_address = address
                break
    return default_address


def get_default_address_text(customer_profile):
    default_address = get_default_address(customer_profile)
    if default_address is None:
        return ""
    parts = [
        default_address.line_1,
        default_address.line_2,
        default_address.landmark,
        default_address.city,
        default_address.state,
        default_address.pincode,
    ]
    return ", ".join(part for part in parts if part)


def serialize_eligible_customer(customer_profile):
    user = customer_profile.customer.user
    default_address = get_default_address(customer_profile)
    return {
        "name": profile_label(customer_profile),
        "phone": str(user.phone) if user.phone else "",
        "user_id": user.id,
        "age": calculate_age(customer_profile.date_of_birth),
        "gender": profile_gender(customer_profile),
        "address": get_default_address_text(customer_profile),
        "pincode": default_address.pincode if default_address else "",
    }


def get_catalog_items_for_city(city, search=""):
    queryset = (
        CatalogItem.objects.filter(
            is_active=True,
            city_prices__city=city,
            city_prices__is_active=True,
        )
        .prefetch_related(
            Prefetch(
                "city_prices",
                queryset=CatalogCityPrice.objects.filter(city=city, is_active=True),
                to_attr="matched_city_prices",
            )
        )
        .distinct()
        .order_by("name")
    )
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset


def create_catalog_item(
    *,
    category,
    is_custom_package,
    name,
    diagnostic_test_id,
    fasting_required,
    city_prices=None,
):
    with transaction.atomic():
        catalog_item = CatalogItem.objects.create(
            category=category,
            is_custom_package=is_custom_package,
            name=name,
            diagnostic_test_id=diagnostic_test_id,
            fasting_required=fasting_required,
        )
        if city_prices:
            CatalogCityPrice.objects.bulk_create(
                [
                    CatalogCityPrice(
                        catalog_item=catalog_item,
                        city=city_price["city"],
                        price=city_price["price"],
                        tat_in_hours=city_price.get("tat_in_hours"),
                    )
                    for city_price in city_prices
                ]
            )
    return catalog_item
