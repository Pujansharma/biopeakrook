from django.db.models import Q, QuerySet

from accounts.customers.models import CustomerProfile
from pre_consultation.models import PreConsultationSession
from pre_consultation.utils.constants import PreConsultationSessionStatus
from test_kit_inventory.utils.constants import TestKitAssignmentStatus


def get_eligible_customer_profile_queryset(search: str = "") -> QuerySet[CustomerProfile]:
    queryset = (
        CustomerProfile.objects.filter(
            customer__user__pre_consultation_session__status=(
                PreConsultationSessionStatus.COMPLETED
            ),
        )
        .exclude(
            test_kit_assignments__status=TestKitAssignmentStatus.ACTIVE,
        )
        .select_related("customer__user")
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


def customer_profile_has_completed_pre_consultation(
    customer_profile: CustomerProfile,
) -> bool:
    return PreConsultationSession.objects.filter(
        user_id=customer_profile.customer.user_id,
        status=PreConsultationSessionStatus.COMPLETED,
    ).exists()


def customer_profile_has_active_test_kit(customer_profile: CustomerProfile) -> bool:
    return customer_profile.test_kit_assignments.filter(
        status=TestKitAssignmentStatus.ACTIVE,
    ).exists()
