"""Layer 1 — sync demographics and address to the selected CustomerProfile."""

from django.db import transaction
from rest_framework import serializers

from accounts.customers.models import CustomerProfile, CustomerProfileAddress
from accounts.customers.utils.constants import AddressType
from accounts.users.models import User
from pre_consultation.gender_mapping import (
    baseline_gender_to_profile_gender,
    profile_gender_to_baseline_gender,
)
from pre_consultation.layers.reset import reset_gender_dependent_medical_history
from pre_consultation.models import PreConsultationSession
from pre_consultation.utils.constants import (
    PreConsultationLayerProgression,
    PatientBaselineGender,
)

DEFAULT_BASELINE_ADDRESS_COUNTRY = "India"

EMPTY_PATIENT_BASELINE_ADDRESS = {
    "line_1": "",
    "line_2": "",
    "city": "",
    "state": "",
    "pin_code": "",
    "residency_type": None,
}

EMPTY_PATIENT_BASELINE_PAYLOAD = {
    "first_name": "",
    "last_name": "",
    "dob": None,
    "gender": None,
    "email_address": "",
    "address": EMPTY_PATIENT_BASELINE_ADDRESS,
}


class PatientBaselineAddressSerializer(serializers.Serializer):
    line_1 = serializers.CharField(max_length=255)
    line_2 = serializers.CharField(
        max_length=255, allow_blank=True, required=False, default=""
    )
    city = serializers.CharField(max_length=100)
    state = serializers.CharField(max_length=100)
    pin_code = serializers.CharField(max_length=20)
    residency_type = serializers.ChoiceField(choices=AddressType.choices)


class PatientBaselineAddressResponseSerializer(serializers.Serializer):
    line_1 = serializers.CharField(max_length=255, allow_blank=True, default="")
    line_2 = serializers.CharField(
        max_length=255, allow_blank=True, required=False, default=""
    )
    city = serializers.CharField(max_length=100, allow_blank=True, default="")
    state = serializers.CharField(max_length=100, allow_blank=True, default="")
    pin_code = serializers.CharField(max_length=20, allow_blank=True, default="")
    residency_type = serializers.ChoiceField(
        choices=AddressType.choices,
        allow_null=True,
        required=False,
    )


class PatientBaselineRequestSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=""
    )
    dob = serializers.DateField()
    gender = serializers.ChoiceField(choices=PatientBaselineGender.choices)
    email_address = serializers.EmailField()
    address = PatientBaselineAddressSerializer()


class PatientBaselineResponseSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=100, allow_blank=True, default="")
    dob = serializers.DateField(allow_null=True, required=False)
    gender = serializers.ChoiceField(
        choices=PatientBaselineGender.choices,
        allow_null=True,
        required=False,
    )
    email_address = serializers.EmailField(allow_blank=True, default="")
    address = PatientBaselineAddressResponseSerializer()


EMPTY_PATIENT_BASELINE_V2_PAYLOAD = {
    "first_name": "",
    "last_name": "",
    "dob": None,
    "gender": None,
    "email_address": "",
    "height": None,
    "weight": None,
    "address": EMPTY_PATIENT_BASELINE_ADDRESS,
}

PATIENT_BASELINE_HEIGHT_CM_MIN = 30.0
PATIENT_BASELINE_HEIGHT_CM_MAX = 300.0
PATIENT_BASELINE_WEIGHT_KG_MIN = 1.0
PATIENT_BASELINE_WEIGHT_KG_MAX = 500.0


class PatientBaselineV2RequestSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default=""
    )
    dob = serializers.DateField()
    gender = serializers.ChoiceField(choices=PatientBaselineGender.choices)
    email_address = serializers.EmailField()
    height = serializers.FloatField(
        min_value=PATIENT_BASELINE_HEIGHT_CM_MIN,
        max_value=PATIENT_BASELINE_HEIGHT_CM_MAX,
        required=False,
        allow_null=True,
    )
    weight = serializers.FloatField(
        min_value=PATIENT_BASELINE_WEIGHT_KG_MIN,
        max_value=PATIENT_BASELINE_WEIGHT_KG_MAX,
        required=False,
        allow_null=True,
    )
    address = PatientBaselineAddressSerializer(required=False)


class PatientBaselineV2ResponseSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=100, allow_blank=True, default="")
    dob = serializers.DateField(allow_null=True, required=False)
    gender = serializers.ChoiceField(
        choices=PatientBaselineGender.choices,
        allow_null=True,
        required=False,
    )
    email_address = serializers.EmailField(allow_blank=True, default="")
    height = serializers.FloatField(allow_null=True, required=False)
    weight = serializers.FloatField(allow_null=True, required=False)
    address = PatientBaselineAddressResponseSerializer()


def get_default_customer_profile_address(
    customer_profile: CustomerProfile,
) -> CustomerProfileAddress | None:
    return (
        CustomerProfileAddress.objects.filter(customer_profile=customer_profile)
        .order_by("-is_default", "-created_at")
        .first()
    )


def customer_profile_address_to_payload(
    customer_profile: CustomerProfile,
) -> dict:
    address = get_default_customer_profile_address(customer_profile)
    if address is None:
        return dict(EMPTY_PATIENT_BASELINE_ADDRESS)
    return {
        "line_1": address.line_1,
        "line_2": address.line_2,
        "city": address.city,
        "state": address.state,
        "pin_code": address.pincode,
        "residency_type": address.address_type,
    }


def customer_profile_to_payload(customer_profile: CustomerProfile) -> dict:
    contact_email = customer_profile.customer.contact_email or ""
    return {
        "first_name": customer_profile.first_name or "",
        "last_name": customer_profile.last_name or "",
        "dob": customer_profile.date_of_birth,
        "gender": profile_gender_to_baseline_gender(customer_profile.gender),
        "email_address": contact_email,
        "address": customer_profile_address_to_payload(customer_profile),
    }


def customer_profile_to_payload_v2(customer_profile: CustomerProfile) -> dict:
    contact_email = customer_profile.customer.contact_email or ""
    return {
        "first_name": customer_profile.first_name or "",
        "last_name": customer_profile.last_name or "",
        "dob": customer_profile.date_of_birth,
        "gender": profile_gender_to_baseline_gender(customer_profile.gender),
        "email_address": contact_email,
        "height": customer_profile.height_cm,
        "weight": customer_profile.weight_kg,
        "address": customer_profile_address_to_payload(customer_profile),
    }


def load_patient_baseline_payload(
    user,
    session: PreConsultationSession,
    customer_profile: CustomerProfile | None = None,
) -> dict:
    if customer_profile is None:
        return EMPTY_PATIENT_BASELINE_PAYLOAD
    return customer_profile_to_payload(customer_profile)


def load_patient_baseline_v2_payload(
    user: User,
    session: PreConsultationSession,
    customer_profile: CustomerProfile | None = None,
) -> dict:
    if customer_profile is None:
        return EMPTY_PATIENT_BASELINE_V2_PAYLOAD
    return customer_profile_to_payload_v2(customer_profile)


def persist_customer_profile_address(
    customer_profile: CustomerProfile,
    address_data: dict,
) -> None:
    residency_type = address_data["residency_type"]
    defaults = {
        "line_1": address_data["line_1"],
        "line_2": address_data.get("line_2", ""),
        "city": address_data["city"],
        "state": address_data["state"],
        "pincode": address_data["pin_code"],
        "address_type": residency_type,
        "country": DEFAULT_BASELINE_ADDRESS_COUNTRY,
        "is_default": True,
    }
    existing_address = get_default_customer_profile_address(customer_profile)
    if existing_address is None:
        CustomerProfileAddress.objects.create(
            customer_profile=customer_profile,
            **defaults,
        )
        return

    CustomerProfileAddress.objects.filter(
        customer_profile=customer_profile,
        is_default=True,
    ).exclude(pk=existing_address.pk).update(is_default=False)
    for field_name, field_value in defaults.items():
        setattr(existing_address, field_name, field_value)
    existing_address.save(update_fields=[*defaults.keys(), "updated_at"])


def persist_patient_baseline_payload(
    user,
    session: PreConsultationSession,
    validated_data: dict,
    customer_profile: CustomerProfile | None = None,
) -> None:
    if customer_profile is None:
        return

    previous_gender = profile_gender_to_baseline_gender(customer_profile.gender)
    previous_dob = customer_profile.date_of_birth
    gender_or_dob_changed = (
        validated_data["gender"] != previous_gender
        or validated_data["dob"] != previous_dob
    )

    address = validated_data["address"]
    profile_gender = baseline_gender_to_profile_gender(validated_data["gender"])

    with transaction.atomic():
        if gender_or_dob_changed:
            reset_gender_dependent_medical_history(session)

        customer_profile.first_name = validated_data["first_name"]
        customer_profile.last_name = validated_data["last_name"]
        customer_profile.date_of_birth = validated_data["dob"]
        customer_profile.gender = profile_gender
        customer_profile.save(
            update_fields=[
                "first_name",
                "last_name",
                "date_of_birth",
                "gender",
                "updated_at",
            ]
        )

        customer = customer_profile.customer
        customer.contact_email = validated_data["email_address"]
        customer.save(update_fields=["contact_email", "updated_at"])

        persist_customer_profile_address(customer_profile, address)

        session.current_layer = PreConsultationLayerProgression.PATIENT_CATEGORY
        session.save(update_fields=["current_layer", "updated_at"])


def persist_patient_baseline_v2_payload(
    user: User,
    session: PreConsultationSession,
    validated_data: dict,
    customer_profile: CustomerProfile | None = None,
) -> None:
    if customer_profile is None:
        return

    previous_gender = profile_gender_to_baseline_gender(customer_profile.gender)
    previous_dob = customer_profile.date_of_birth
    gender_or_dob_changed = (
        validated_data["gender"] != previous_gender
        or validated_data["dob"] != previous_dob
    )

    profile_gender = baseline_gender_to_profile_gender(validated_data["gender"])

    with transaction.atomic():
        if gender_or_dob_changed:
            reset_gender_dependent_medical_history(session)

        customer_profile.first_name = validated_data["first_name"]
        customer_profile.last_name = validated_data["last_name"]
        customer_profile.date_of_birth = validated_data["dob"]
        customer_profile.gender = profile_gender
        update_fields = [
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "updated_at",
        ]
        if "height" in validated_data:
            customer_profile.height_cm = validated_data["height"]
            update_fields.append("height_cm")
        if "weight" in validated_data:
            customer_profile.weight_kg = validated_data["weight"]
            update_fields.append("weight_kg")
        customer_profile.save(update_fields=update_fields)

        customer = customer_profile.customer
        customer.contact_email = validated_data["email_address"]
        customer.save(update_fields=["contact_email", "updated_at"])

        address = validated_data.get("address")
        if address is not None:
            persist_customer_profile_address(customer_profile, address)

        session.current_layer = PreConsultationLayerProgression.PATIENT_GOALS_PRIORITIES
        session.save(update_fields=["current_layer", "updated_at"])
