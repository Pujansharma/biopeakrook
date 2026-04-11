from accounts.customers.models import Customer, CustomerProfile
from accounts.customers.serializers import (
    CustomerAccountSerializer,
    CustomerProfileSerializer
)
from accounts.utils.permissions import IsCustomerUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListAPIView, BaseRetrieveUpdateAPIView
)


class CustomerAccountProfileView(BaseRetrieveUpdateAPIView):
    """Views for customers to update their profiles"""
    permission_classes = [IsCustomerUser]
    serializer_class = CustomerAccountSerializer

    def get_object(self):
        qs = Customer.objects.select_related(
            'user'
        )
        return get_object_or_404(
            qs, detail="Invalid Customer profile",
            pk=self.kwargs.get('pk')
        )


class CustomerProfilesListView(BaseListAPIView):
    """View for customers to List all profiles"""
    permission_classes = [IsCustomerUser]
    serializer_class = CustomerProfileSerializer

    def get_customer(self):
        qs = Customer.objects.select_related(
            'user'
        )
        return get_object_or_404(
            qs, detail="Invalid Customer profile",
            pk=self.kwargs.get('pk')
        )

    def get_queryset(self):
        return CustomerProfile.objects.select_related(
            'customer__user'
        ).filter(
            customer=self.get_customer()
        )
