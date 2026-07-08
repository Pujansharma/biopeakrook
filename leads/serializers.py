from django.db import transaction
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
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
from leads.utils.helper import create_customer_profile_from_lead

User = get_user_model()


class BaseLeadSerializer(BaseModelSerializer):
    phone = PhoneNumberSerializerField()
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
            "is_request_sent",
            "is_onboarding_sent",
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
                phone, email, first_name, last_name, gender, age, date_of_birth
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
        was_converted = bool(instance.customer_profile or instance.converted_on)

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
            if not lead_data.get("metsights_profile_id"):
                metsights_profile_id = get_or_create_metsights_profile(
                    lead.phone,
                    lead.email,
                    lead.first_name,
                    lead.last_name,
                    lead.gender,
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

        if lead.customer_profile or lead.converted_on:
            raise serializers.ValidationError("Lead is already converted to client.")
        if not lead.home_center:
            raise serializers.ValidationError(
                {"home_center": "Home center is required before conversion."}
            )
        if User.objects.filter(phone=lead.phone).exists():
            raise serializers.ValidationError(
                {"phone": "A customer user with this phone already exists."}
            )

        with transaction.atomic():
            create_customer_profile_from_lead(lead, updated_by)

        return lead
