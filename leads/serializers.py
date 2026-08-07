from django.db import transaction
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
from accounts.customers.serializers import BaseCustomerProfileSerializer
from accounts.users.serializers import BaseUserSerializer
from accounts.utils.auth import get_user_model
from accounts.utils.helper import get_date_of_birth_from_age
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer
from integrations.metsights.helper import get_or_create_metsights_profile
from leads.models import Lead
from leads.utils.db import (
    decrement_leads_assigned,
    decrement_leads_inactive,
    generate_lead_unique_id,
    increment_leads_assigned,
    increment_leads_inactive,
    increment_leads_total,
)
from leads.utils.helper import convert_lead_to_client

User = get_user_model()


class BaseLeadSerializer(BaseModelSerializer):
    phone = PhoneNumberSerializerField()
    customer_profile = BaseCustomerProfileSerializer(read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    updated_by = BaseUserSerializer(read_only=True)
    home_center = BaseCenterSerializer(read_only=True)
    home_center_id = serializers.UUIDField(required=False, write_only=True)
    age = serializers.FloatField(required=False, write_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "unique_id",
            "first_name",
            "last_name",
            "gender",
            "age",
            "date_of_birth",
            "phone",
            "email",
            "description",
            "is_active",
            "is_client",
            "is_invited",
            "is_joined",
            "is_onboarding_sent",
            "converted_on",
            "packages",
            "home_center",
            "home_center_id",
            "customer_profile",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "unique_id",
            "is_joined",
            "converted_on",
            "customer_profile",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]


class LeadListCreateSerializer(BaseLeadSerializer):
    def create(self, validated_data: dict) -> Lead:
        age = validated_data.pop("age", None)
        date_of_birth = validated_data.get("date_of_birth", None)
        phone = validated_data.get("phone")
        email = validated_data.get("email")
        first_name = validated_data.get("first_name")
        last_name = validated_data.get("last_name")
        gender = validated_data.get("gender")

        exists = Lead.objects.filter(phone=phone).exists()
        if exists:
            raise serializers.ValidationError({
                "phone": "Lead with this phone number already exists"
            })

        if age and not date_of_birth:
            date_of_birth = get_date_of_birth_from_age(age)
            validated_data["date_of_birth"] = date_of_birth

        validated_data["unique_id"] = generate_lead_unique_id()
        home_center_id = validated_data.pop("home_center_id", None)
        if home_center_id:
            home_center = Center.objects.filter(pk=home_center_id).first()
            if not home_center:
                raise serializers.ValidationError(
                    {"home_center_id": "Invalid center ID provided"}
                )
            validated_data["home_center"] = home_center

        with transaction.atomic():
            lead = super().create(validated_data)
            increment_leads_total()
            if not lead.is_active:
                increment_leads_inactive()
            metsights_profile_id = get_or_create_metsights_profile(
                phone=phone,
                email=email,
                first_name=first_name,
                last_name=last_name,
                gender=gender,
                age=age,
                date_of_birth=date_of_birth
            )
            if metsights_profile_id:
                lead.data = {
                    **(lead.data or {}),
                    "metsights_profile_id": metsights_profile_id,
                }
                lead.save(update_fields=["data"])
        return lead


class LeadDetailSerializer(BaseLeadSerializer):
    home_center_id = serializers.UUIDField(required=False)

    def update(self, instance: Lead, validated_data: dict) -> Lead:
        was_active = instance.is_active
        was_joined = instance.is_joined
        was_onboarding_sent = instance.is_onboarding_sent
        was_converted = bool(instance.customer_profile or instance.converted_on)
        phone = validated_data.get('phone', instance.phone)
        exists = Lead.objects.exclude(pk=instance.pk).filter(phone=phone).exists()
        if exists:
            raise serializers.ValidationError({
                "phone": "Lead with this phone number already exists"
            })

        home_center_id = validated_data.pop("home_center_id", None)
        if home_center_id:
            home_center = Center.objects.filter(pk=home_center_id).first()
            if not home_center:
                raise serializers.ValidationError(
                    {"home_center_id": "Invalid center ID provided"}
                )
            validated_data["home_center"] = home_center
        age = validated_data.pop("age", None)
        date_of_birth = validated_data.get("date_of_birth", None)

        if age and not date_of_birth:
            date_of_birth = get_date_of_birth_from_age(age)
            validated_data["date_of_birth"] = date_of_birth
        with transaction.atomic():
            lead = super().update(instance, validated_data)
            lead_data = lead.data or {}
            if was_active and not lead.is_active:
                increment_leads_inactive()
            if not was_active and lead.is_active:
                decrement_leads_inactive()
            if not was_joined and lead.is_joined:
                increment_leads_assigned()
            if was_joined and not lead.is_joined and not was_converted:
                decrement_leads_assigned()
            if (
                lead.customer_profile_id is not None
                and lead.is_onboarding_sent != was_onboarding_sent
            ):
                lead.customer_profile.is_onboarding_sent = lead.is_onboarding_sent
                lead.customer_profile.save(
                    update_fields=["is_onboarding_sent", "updated_at"]
                )
            if not lead_data.get("metsights_profile_id"):
                metsights_profile_id = get_or_create_metsights_profile(
                    phone=lead.phone,
                    email=lead.email,
                    first_name=lead.first_name,
                    last_name=lead.last_name,
                    gender=lead.gender,
                    age=None,
                    date_of_birth=lead.date_of_birth,
                )
                if metsights_profile_id:
                    lead.data = {
                        **lead_data,
                        "metsights_profile_id": metsights_profile_id,
                    }
                    lead.save(update_fields=["data"])
        return lead


class LeadConvertClientSerializer(BaseModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id",
            "is_client",
            "is_joined",
            "converted_on",
            "customer_profile",
        ]
        read_only_fields = fields

    def create(self, validated_data: dict) -> Lead:
        lead = validated_data["lead"]
        updated_by = validated_data.get("updated_by")

        if lead.customer_profile_id is not None and lead.customer_profile.is_converted:
            raise serializers.ValidationError("Lead is already converted to client.")
        if not lead.home_center:
            raise serializers.ValidationError(
                {"home_center": "Home center is required before conversion."}
            )

        try:
            with transaction.atomic():
                convert_lead_to_client(lead, updated_by)
        except ValueError as error:
            raise serializers.ValidationError(str(error)) from error

        lead.refresh_from_db()
        return lead
