from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
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
from accounts.users.serializers import BaseUserSerializer
from accounts.utils.auth import get_user_model
from core.utils.fields import PhoneNumberSerializerField
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from leads.models import Lead
from leads.utils.db import (
    decrement_leads_assigned,
    decrement_leads_inactive,
    generate_lead_unique_id,
    increment_leads_assigned,
    increment_leads_converted,
    increment_leads_inactive,
    increment_leads_total,
    share_onboarding_form,
)

User = get_user_model()


class BaseLeadSerializer(BaseModelSerializer):
    phone = PhoneNumberSerializerField()
    created_by = BaseUserSerializer(read_only=True)
    updated_by = BaseUserSerializer(read_only=True)
    home_center = BaseCenterSerializer(read_only=True)
    home_center_id = serializers.UUIDField(required=False)

    class Meta:
        model = Lead
        fields = [
            "id",
            "unique_id",
            "first_name",
            "last_name",
            "gender",
            "phone",
            "email",
            "description",
            "is_active",
            "is_client",
            "is_request_sent",
            "is_onboarding_sent",
            "converted_on",
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
            if lead.is_client:
                increment_leads_assigned()
        return lead


class LeadDetailSerializer(BaseLeadSerializer):
    home_center_id = serializers.UUIDField(required=False)

    def update(self, instance: Lead, validated_data: dict) -> Lead:
        was_active = instance.is_active
        was_client = instance.is_client
        was_converted = bool(instance.customer_profile or instance.converted_on)

        home_center_id = validated_data.pop("home_center_id", None)
        if home_center_id:
            home_center = Center.objects.filter(pk=home_center_id).first()
            if not home_center:
                raise serializers.ValidationError(
                    {"home_center_id": "Invalid center ID provided"}
                )
            validated_data["home_center"] = home_center

        with transaction.atomic():
            lead = super().update(instance, validated_data)
            if was_active and not lead.is_active:
                increment_leads_inactive()
            if not was_active and lead.is_active:
                decrement_leads_inactive()
            if not was_client and lead.is_client:
                increment_leads_assigned()
            if was_client and not lead.is_client and not was_converted:
                decrement_leads_assigned()

        return lead


class LeadShareOnboardingSerializer(BaseModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id",
            "is_request_sent",
            "is_onboarding_sent",
        ]
        read_only_fields = fields

    def create(self, validated_data: dict) -> Lead:
        lead = validated_data["lead"]
        created_by = validated_data.get("created_by")
        share_onboarding_form()
        lead.is_request_sent = True
        lead.is_onboarding_sent = True
        lead.updated_by = created_by
        lead.save(
            update_fields=[
                "is_request_sent",
                "is_onboarding_sent",
                "updated_by",
                "updated_at",
            ]
        )
        return lead


class LeadConvertClientSerializer(BaseModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id",
            "is_client",
            "converted_on",
            "customer_profile",
        ]
        read_only_fields = fields

    def create(self, validated_data: dict) -> Lead:
        lead = validated_data["lead"]
        updated_by = validated_data.get("updated_by")

        if lead.customer_profile or lead.converted_on:
            raise serializers.ValidationError("Lead is already converted to client.")
        if not lead.is_client:
            raise serializers.ValidationError(
                "Lead must be marked as client before conversion."
            )
        if not lead.home_center:
            raise serializers.ValidationError(
                {"home_center": "Home center is required before conversion."}
            )
        if User.objects.filter(phone__iexact=lead.phone).exists():
            raise serializers.ValidationError(
                {"phone": "A customer user with this phone already exists."}
            )

        profile_data = {
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "gender": lead.gender,
        }

        with transaction.atomic():
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
            lead.updated_by = updated_by
            lead.save(
                update_fields=[
                    "customer_profile",
                    "converted_on",
                    "updated_by",
                    "updated_at",
                ]
            )
            increment_leads_converted()

        return lead


class LeadAvailableCompositeSerializer(BaseSerializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class CompositeIDSerializer(BaseSerializer):
    id = serializers.UUIDField(write_only=True)


class LeadAssignCompositeSerializer(BaseSerializer):
    add = CompositeIDSerializer(many=True, required=False, write_only=True)
    remove = CompositeIDSerializer(many=True, required=False, write_only=True)

    def create(self, validated_data: dict) -> dict:
        add_ids = validated_data.get("add", [])
        remove_ids = validated_data.get("remove", [])

        if not add_ids and not remove_ids:
            raise serializers.ValidationError(
                "At least one of 'add' or 'remove' must be provided."
            )

        raise serializers.ValidationError(
            "Composite package assignment is unavailable until composite models are implemented."
        )


class LeadCompositeAssignmentSerializer(BaseSerializer):
    id = serializers.UUIDField(read_only=True)
    composite = LeadAvailableCompositeSerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
