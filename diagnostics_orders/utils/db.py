from datetime import timedelta

from django.db.models import Count, F, Prefetch, Q
from django.utils import timezone

from accounts.customers.models import CustomerProfile
from diagnostics_orders.models import (
    CatalogCityPrice,
    CatalogItem,
    DiagnosticOrder,
    DiagnosticOrderCustomer,
    DiagnosticOrderLine,
    DiagnosticsOrdersSummary,
)
from diagnostics_orders.utils.constants import (
    CollectionDateFilter,
    TERMINAL_ORDER_STATUSES,
)
from diagnostics_orders.utils.helpers import calculate_age, profile_label
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
    return DiagnosticOrderCustomer.objects.filter(
        customer_profile=customer_profile,
        order__is_active=True,
    ).exclude(order__status__in=TERMINAL_ORDER_STATUSES).exists()


def get_eligible_customer_profile_queryset(search="", center_id=None):
    active_order_profile_ids = DiagnosticOrderCustomer.objects.filter(
        order__is_active=True,
    ).exclude(order__status__in=TERMINAL_ORDER_STATUSES).values_list(
        "customer_profile_id", flat=True
    )

    queryset = (
        CustomerProfile.objects.filter(
            is_active=True,
            customer__user__pre_consultation_session__status=(
                PreConsultationSessionStatus.COMPLETED
            ),
            programs__is_active=True,
            programs__cancelled_at__isnull=True,
            center_assignments__is_active=True,
        )
        .exclude(id__in=active_order_profile_ids)
        .annotate(
            previous_diagnostic_orders_count=Count(
                "diagnostic_order_customers__order",
                filter=Q(
                    diagnostic_order_customers__order__is_active=True,
                    diagnostic_order_customers__order__status__in=TERMINAL_ORDER_STATUSES,
                ),
                distinct=True,
            )
        )
        .select_related("customer__user")
        .prefetch_related("addresses")
        .order_by("-created_at")
        .distinct()
    )

    if center_id:
        queryset = queryset.filter(center_assignments__center_id=center_id)

    if not search:
        return queryset

    search_query = Q()
    search_query |= Q(first_name__istartswith=search)
    search_query |= Q(last_name__istartswith=search)
    search_query |= Q(first_name__icontains=search)
    search_query |= Q(last_name__icontains=search)
    search_query |= Q(customer__user__phone__icontains=search)
    return queryset.filter(search_query)


def get_default_address_text(customer_profile):
    addresses = list(customer_profile.addresses.all())
    if not addresses:
        return ""
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
    return {
        "label": profile_label(customer_profile),
        "phone": str(user.phone) if user.phone else "",
        "user_id": user.id,
        "age": calculate_age(customer_profile.date_of_birth),
        "gender": customer_profile.gender,
        "address": get_default_address_text(customer_profile),
        "previous_diagnostic_orders_count": getattr(
            customer_profile, "previous_diagnostic_orders_count", 0
        ),
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


def get_orders_queryset(
    search="",
    status=None,
    cities=None,
    collection_date=None,
):
    queryset = (
        DiagnosticOrder.objects.filter(is_active=True)
        .prefetch_related("customers")
        .order_by("-created_at")
    )
    if status:
        queryset = queryset.filter(status=status)
    if cities:
        queryset = queryset.filter(city__in=cities)
    if search:
        search_query = Q(request_id__icontains=search)
        search_query |= Q(address__icontains=search)
        search_query |= Q(customers__name__icontains=search)
        queryset = queryset.filter(search_query).distinct()

    if collection_date and collection_date != CollectionDateFilter.ALL:
        now = timezone.localdate()
        if collection_date == CollectionDateFilter.TODAY:
            queryset = queryset.filter(slot_datetime__date=now)
        elif collection_date == CollectionDateFilter.TOMORROW:
            queryset = queryset.filter(slot_datetime__date=now + timedelta(days=1))
        elif collection_date == CollectionDateFilter.PAST_7_DAYS:
            queryset = queryset.filter(
                slot_datetime__date__gte=now - timedelta(days=7),
                slot_datetime__date__lte=now,
            )
        elif collection_date == CollectionDateFilter.UPCOMING:
            queryset = queryset.filter(slot_datetime__date__gt=now)
    return queryset


def get_order_detail_queryset():
    return DiagnosticOrder.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            "customers",
            queryset=DiagnosticOrderCustomer.objects.prefetch_related(
                Prefetch(
                    "lines",
                    queryset=DiagnosticOrderLine.objects.all(),
                )
            ),
        )
    )


def get_order_by_request_id(request_id):
    return get_order_detail_queryset().get(request_id=request_id)
