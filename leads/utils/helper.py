from django.utils import timezone

from accounts.centers.utils.db import increment_customer_count
from accounts.customers.models import (
    Customer,
    CustomerCenterAssignment,
    CustomerProfile,
)
from accounts.customers.utils.db import (
    create_customer_user_account,
    increment_centers_count,
)
from accounts.organizations.utils.db import increment_organization_clients_count
from accounts.utils.auth import get_user_model
from leads.models import Lead
from leads.utils.db import (
    increment_leads_assigned,
    increment_leads_converted,
)

User = get_user_model()


def create_customer_profile_from_lead(lead: Lead, updated_by: User) -> CustomerProfile:
    was_joined = lead.is_joined
    profile_data = {
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "gender": lead.gender,
    }

    user = User.objects.create_user(
        email=None,
        password=None,
        phone=lead.phone,
        **profile_data,
    )
    customer = Customer.objects.create(
        user=user,
        contact_email=lead.email,
        created_by=updated_by,
    )
    customer_profile = CustomerProfile.objects.create(
        customer=customer,
        is_main=True,
        created_by=updated_by,
        **profile_data,
    )
    CustomerCenterAssignment.objects.create(
        customer_profile=customer_profile,
        center=lead.home_center,
        is_primary=True,
        created_by=updated_by,
    )
    create_customer_user_account(customer)
    increment_customer_count(lead.home_center.pk)
    increment_centers_count(customer_profile.pk)
    increment_organization_clients_count()

    lead.customer_profile = customer_profile
    lead.converted_on = timezone.now()
    lead.is_joined = True
    lead.updated_by = updated_by
    lead.save(
        update_fields=[
            "customer_profile",
            "converted_on",
            "is_joined",
            "updated_by",
            "updated_at",
        ]
    )
    increment_leads_converted()
    if not was_joined:
        increment_leads_assigned()

    return customer_profile
