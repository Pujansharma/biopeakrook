from django.db.models import Q

from accounts.customers.models import CustomerProfileAddress
from accounts.customers.serializers import CustomerProfileAddressSerializer
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.views.main import BaseRetrieveUpdateDestroyAPIView


class CustomerProfileAddressDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = CustomerProfileAddressSerializer
    permission_classes = [IsAdminUser | IsAssociateUser | IsCustomerUser]

    def get_queryset(self):
        filter_kwargs = {}
        query_filter = Q()

        user = self.request.user
        account_type = get_user_account_type(user)

        if account_type == UserType.CUSTOMER:
            customer = getattr(user, "customer")
            filter_kwargs["customer_profile__customer"] = customer
        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate")
            query_filter = Q(
                customer_profile__center_assignments__center__associate_assignments__associate=associate
            ) | Q(customer_profile__associate_assignments__associate=associate)

        qs = (
            CustomerProfileAddress.objects.select_related(
                "customer_profile",
                "customer_profile__customer",
            )
            .filter(query_filter, **filter_kwargs)
            .distinct()
        )
        return qs
