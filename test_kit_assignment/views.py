from django.db.models import Q

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.views.main import BaseCreateAPIView, BaseListAPIView
from test_kit_assignment.models import TestKitAssignment
from test_kit_assignment.serializers import (
    EligibleCustomerProfileSerializer,
    TestKitAssignmentCreateSerializer,
    TestKitAssignmentHistorySerializer,
)
from test_kit_assignment.utils.db import get_eligible_customer_profile_queryset


class TestKitEligibleCustomerListView(BaseListAPIView):
    serializer_class = EligibleCustomerProfileSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        return get_eligible_customer_profile_queryset(search)


class TestKitAssignmentCreateView(BaseCreateAPIView):
    serializer_class = TestKitAssignmentCreateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.send_response(self.get_create_success_message(), status=201)


class TestKitAssignmentHistoryListView(BaseListAPIView):
    serializer_class = TestKitAssignmentHistorySerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = self.request.query_params.get("search", "").strip()
        queryset = (
            TestKitAssignment.objects.select_related(
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
