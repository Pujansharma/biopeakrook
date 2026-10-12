from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import NotFound

from accounts.customers.models import CustomerProfile
from accounts.customers.utils.db import get_customer_profile_for_user
from core.utils.helper import get_request_ip_address, get_request_user_agent
from wearables.models import RookMemberIdentity, WearableConsent
from wearables.utils.constants import ConsentStatus, PreferredUnits


def resolve_customer_profile(request) -> CustomerProfile:
    customer_profile = get_customer_profile_for_user(
        request.user,
        getattr(request, "customer_profile_id", None),
    )
    if customer_profile is None:
        raise NotFound("Customer profile not found for this account.")
    return customer_profile


def rook_user_id_for_profile(customer_profile: CustomerProfile) -> str:
    return f"bp{customer_profile.pk.hex}"


def get_or_create_rook_identity(
    customer_profile: CustomerProfile,
    *,
    timezone_name: str | None = None,
    preferred_units: str | None = None,
) -> RookMemberIdentity:
    defaults = {
        "rook_user_id": rook_user_id_for_profile(customer_profile),
        "timezone_name": timezone_name or settings.TIME_ZONE,
        "preferred_units": preferred_units or PreferredUnits.METRIC,
    }
    identity, created = RookMemberIdentity.objects.get_or_create(
        customer_profile=customer_profile,
        defaults=defaults,
    )
    update_fields = []
    if not created and timezone_name and identity.timezone_name != timezone_name:
        identity.timezone_name = timezone_name
        update_fields.append("timezone_name")
    if not created and preferred_units and identity.preferred_units != preferred_units:
        identity.preferred_units = preferred_units
        update_fields.append("preferred_units")
    if update_fields:
        update_fields.append("updated_at")
        identity.save(update_fields=update_fields)
    return identity


def record_wearable_consent(
    *,
    request,
    customer_profile: CustomerProfile,
    consent_version: str,
) -> WearableConsent:
    now = timezone.now()
    active_consent = (
        WearableConsent.objects.filter(
            customer_profile=customer_profile,
            status=ConsentStatus.GRANTED,
            version=consent_version,
            revoked_at__isnull=True,
        )
        .order_by("-granted_at")
        .first()
    )
    if active_consent is not None:
        return active_consent
    return WearableConsent.objects.create(
        customer_profile=customer_profile,
        granted_by=request.user,
        status=ConsentStatus.GRANTED,
        version=consent_version,
        granted_at=now,
        ip_address=get_request_ip_address(request),
        user_agent=(get_request_user_agent(request) or "")[:512],
    )

