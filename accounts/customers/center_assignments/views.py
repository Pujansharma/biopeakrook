from django.db import transaction
from django.db.models import QuerySet

from accounts.centers.utils.db import decrement_customer_count
from accounts.customers.center_assignments.serializers import (
    CustomerCenterAssignmentDetailSerializer,
)
from accounts.customers.models import CustomerCenterAssignment
from accounts.customers.utils.db import compute_customer_profile_center_counts
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.permissions import ReadOnly
from core.utils.views import BaseRetrieveUpdateDestroyAPIView


class CustomerCenterAssignmentDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = CustomerCenterAssignmentDetailSerializer
    permission_classes = [
        IsAdminUser | IsAssociateUser | (IsCustomerUser & ReadOnly)
    ]

    def get_queryset(self) -> QuerySet[CustomerCenterAssignment]:
        filter_kwargs = {}
        user = self.request.user
        account_type = get_user_account_type(user)

        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate")
            filter_kwargs["center__associate_assignments__associate"] = associate

        if account_type == UserType.CUSTOMER:
            customer = getattr(user, "customer")
            filter_kwargs["customer_profile__customer"] = customer

        return CustomerCenterAssignment.objects.select_related(
            "customer_profile__customer__user",
            "center",
            "created_by",
        ).filter(**filter_kwargs)

    def perform_destroy(self, instance: CustomerCenterAssignment) -> None:
        if instance.is_primary:
            self.raise_bad_request(
                "The primary center assignment cannot be deleted."
            )

        with transaction.atomic():
            center = instance.center
            customer_profile = instance.customer_profile
            super().perform_destroy(instance)
            decrement_customer_count(center.pk)
            compute_customer_profile_center_counts(customer_profile.pk)
