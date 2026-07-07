"""Resolve X-Customer-Profile-ID (or main profile) for baseline/medical layers."""

from rest_framework.exceptions import NotFound, ValidationError

from accounts.customers.models import Customer, CustomerProfile
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type


def resolve_customer_profile_for_request(
    user,
    customer_profile_id: str | None,
) -> CustomerProfile:
    account_type = get_user_account_type(user)
    # if account_type != UserType.CUSTOMER:
    #     raise ValidationError("Pre-consultation requires a customer account.")

    customer = Customer.objects.filter(user=user).first()
    if customer is None:
        raise NotFound("Customer account not found.")

    if customer_profile_id:
        profile = CustomerProfile.objects.filter(
            pk=customer_profile_id,
            customer=customer,
        ).first()
        if profile is None:
            raise NotFound("Customer profile not found.")
        return profile

    profile = CustomerProfile.objects.filter(customer=customer, is_main=True).first()
    if profile is None:
        raise NotFound("Customer profile not found.")
    return profile
