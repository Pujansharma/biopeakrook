from django.db.models import F

from diagnostics_orders.models import (
    CatalogItem,
    DiagnosticOrderCustomer,
    DiagnosticsOrdersSummary,
)
from diagnostics_orders.utils.constants import TERMINAL_ORDER_STATUSES
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


def get_catalog_items(search=""):
    queryset = CatalogItem.objects.filter(is_active=True).order_by("name")
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset


def create_catalog_item(*, test_id, name, price):
    return CatalogItem.objects.create(test_id=test_id, name=name, price=price)
