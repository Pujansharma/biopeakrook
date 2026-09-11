from accounts.customers.models import CustomerProfile
from integrations.metsights.models import MetsightsProfile
from integrations.metsights.sdk import create_metsights_profile


def create_metsights_profile_for_customer_profile(customer_profile: CustomerProfile):
    """
    Updated function which creates a metsights customer profile & saves the profile ID mapping in the DB
    """

    metsights_profile = MetsightsProfile.objects.filter(
        customer_profile=customer_profile
    ).first()

    if not metsights_profile:
        _response = create_metsights_profile(
            phone=customer_profile.customer.user.phone,
            email=customer_profile.customer.contact_email,
            first_name=customer_profile.first_name,
            last_name=customer_profile.last_name,
            gender=customer_profile.gender,
            age=None,
            date_of_birth=customer_profile.date_of_birth,
        )
        profile_id = _response.get('id')
        metsights_profile, _ = MetsightsProfile.objects.update_or_create(
            customer_profile, defaults={
                'profile_id': profile_id
            }
        )

    return metsights_profile
