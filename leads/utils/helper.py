from django.db import IntegrityError, transaction
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

USER_PHONE_EXISTS_ERROR = "A customer with this phone number already exists."


def _lead_user_profile_data(lead: Lead) -> dict:
    return {
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "gender": lead.gender,
        "date_of_birth": lead.date_of_birth,
    }


def _lead_customer_profile_data(lead: Lead) -> dict:
    return _lead_user_profile_data(lead)


def _fill_missing_profile_fields(
    target: User | CustomerProfile,
    lead_data: dict,
) -> None:
    update_fields = []
    for field_name, value in lead_data.items():
        if value is None:
            continue
        if getattr(target, field_name) is not None:
            continue
        setattr(target, field_name, value)
        update_fields.append(field_name)
    if not update_fields:
        return
    update_fields.append("updated_at")
    target.save(update_fields=update_fields)


def _sync_lead_profile_fields(
    lead: Lead,
    user: User,
    customer_profile: CustomerProfile,
) -> None:
    profile_data = _lead_customer_profile_data(lead)
    _fill_missing_profile_fields(user, profile_data)
    _fill_missing_profile_fields(customer_profile, profile_data)


def sync_shell_from_lead(lead: Lead) -> None:
    if lead.customer_profile_id is None:
        return

    customer_profile = lead.customer_profile
    customer = customer_profile.customer
    user = customer.user
    profile_data = _lead_customer_profile_data(lead)

    with transaction.atomic():
        user_update_fields = []
        for field_name, value in profile_data.items():
            setattr(user, field_name, value)
            user_update_fields.append(field_name)
        user_update_fields.append("updated_at")
        user.save(update_fields=user_update_fields)

        profile_update_fields = []
        for field_name, value in profile_data.items():
            setattr(customer_profile, field_name, value)
            profile_update_fields.append(field_name)
        customer_profile.is_onboarding_sent = lead.is_onboarding_sent
        profile_update_fields.extend(["is_onboarding_sent", "updated_at"])
        customer_profile.save(update_fields=profile_update_fields)

        customer.contact_email = lead.email
        customer.save(update_fields=["contact_email", "updated_at"])


def create_shell_customer_from_lead(
    lead: Lead,
    created_by: User | None = None,
) -> User:
    if User.objects.filter(phone__iexact=lead.phone).exists():
        raise ValueError(USER_PHONE_EXISTS_ERROR)

    user_profile_data = _lead_user_profile_data(lead)
    customer_profile_data = _lead_customer_profile_data(lead)

    with transaction.atomic():
        try:
            user = User.objects.create_user(
                email=None,
                password=None,
                phone=lead.phone,
                **user_profile_data,
            )
        except IntegrityError as error:
            raise ValueError(USER_PHONE_EXISTS_ERROR) from error

        customer = Customer.objects.create(
            user=user,
            contact_email=lead.email,
            created_by=created_by,
        )
        create_customer_user_account(customer)
        customer_profile = CustomerProfile.objects.create(
            customer=customer,
            is_main=True,
            is_converted=False,
            is_onboarding_sent=lead.is_onboarding_sent,
            created_by=created_by,
            **customer_profile_data,
        )
        lead.customer_profile = customer_profile
        lead.save(update_fields=["customer_profile", "updated_at"])

    return user


def _ensure_customer_center_assignment(
    lead: Lead,
    customer_profile: CustomerProfile,
    updated_by: User | None,
) -> CustomerCenterAssignment:
    assignment = CustomerCenterAssignment.objects.filter(
        customer_profile=customer_profile,
        center=lead.home_center,
    ).first()
    if assignment is not None:
        return assignment

    assignment = CustomerCenterAssignment.objects.create(
        customer_profile=customer_profile,
        center=lead.home_center,
        is_primary=True,
        created_by=updated_by,
    )
    increment_customer_count(lead.home_center.pk)
    increment_centers_count(customer_profile.pk)
    increment_organization_clients_count()
    return assignment


def _mark_lead_converted(lead: Lead, updated_by: User | None) -> None:
    was_joined = lead.is_joined
    was_converted = lead.converted_on is not None

    lead.is_client = True
    lead.is_joined = True
    lead.converted_on = timezone.now()
    lead.updated_by = updated_by
    lead.save(
        update_fields=[
            "is_client",
            "is_joined",
            "converted_on",
            "updated_by",
            "updated_at",
        ]
    )

    if not was_converted:
        increment_leads_converted()
    if not was_joined:
        increment_leads_assigned()


def _finalize_lead_conversion(
    lead: Lead,
    customer_profile: CustomerProfile,
    updated_by: User | None,
) -> CustomerProfile:
    with transaction.atomic():
        _sync_lead_profile_fields(
            lead,
            customer_profile.customer.user,
            customer_profile,
        )

        if not customer_profile.is_converted:
            customer_profile.is_converted = True
            customer_profile.save(update_fields=["is_converted", "updated_at"])

        if lead.home_center_id is not None:
            _ensure_customer_center_assignment(lead, customer_profile, updated_by)

        if lead.customer_profile_id != customer_profile.pk:
            lead.customer_profile = customer_profile
            lead.save(update_fields=["customer_profile", "updated_at"])

        _mark_lead_converted(lead, updated_by)

    return customer_profile


def _create_user_customer_profile_from_lead(
    lead: Lead,
    updated_by: User | None,
) -> CustomerProfile:
    create_shell_customer_from_lead(lead, created_by=updated_by)
    return lead.customer_profile


def convert_lead_to_client(lead: Lead, updated_by: User | None) -> CustomerProfile:
    if not lead.home_center_id:
        raise ValueError("Home center is required before conversion.")

    if lead.customer_profile_id is not None:
        customer_profile = lead.customer_profile
        if customer_profile.is_converted:
            raise ValueError("Lead is already converted to client.")
        return _finalize_lead_conversion(lead, customer_profile, updated_by)

    user = User.objects.filter(phone__iexact=lead.phone, is_active=True).first()
    if user is not None:
        customer = Customer.objects.filter(user=user).first()
        if customer is None:
            customer = Customer.objects.create(
                user=user,
                contact_email=lead.email,
                created_by=updated_by,
            )
            create_customer_user_account(customer)

        customer_profile = CustomerProfile.objects.filter(
            customer=customer,
            is_main=True,
        ).first()
        if customer_profile is None:
            customer_profile = CustomerProfile.objects.create(
                customer=customer,
                is_main=True,
                is_converted=False,
                created_by=updated_by,
                **_lead_customer_profile_data(lead),
            )

        return _finalize_lead_conversion(lead, customer_profile, updated_by)

    customer_profile = _create_user_customer_profile_from_lead(lead, updated_by)
    return _finalize_lead_conversion(lead, customer_profile, updated_by)


def create_customer_profile_from_lead(
    lead: Lead,
    updated_by: User | None,
) -> CustomerProfile:
    return convert_lead_to_client(lead, updated_by)
