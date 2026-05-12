from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer, MinimumCenterSerializer
from accounts.customers.models import CustomerProfile
from accounts.customers.serializers import (
    CustomerProfileWithCenterSerializer,
    BaseCustomerProfileSerializer,
)
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from services.models import Service
from services.programs.models import (
    Program,
    WellnessProgram,
    ProgramService,
    RedemptionHistory,
)
from services.programs.utils.constants import ProgramType
from services.programs.utils.db import (
    cancel_program_services,
    update_program_redeemable_centers_count,
    update_program_services_count,
    update_program_sessions_count,
)
from services.serializers import BaseServiceSerializer
from services.utils.db import redeem_all_program_services


class BaseProgramSerializer(BaseModelSerializer):
    profile = BaseCustomerProfileSerializer(source="customer_profile", read_only=True)

    class Meta:
        model = Program
        fields = [
            "id",
            "profile",
            "program_type",
            "notes",
            "expires_at",
            "is_complimentary",
            "price",
            "services_count",
            "sessions_count",
            "sessions_used",
            "redeemable_centers_count",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ProgramSerializer(BaseModelSerializer):
    class Meta:
        model = Program
        fields = ["id"]


class BaseProgramServiceSerializer(BaseModelSerializer):
    service = BaseServiceSerializer(read_only=True)
    cancelled_by = BaseUserSerializer(read_only=True)
    can_redeem = serializers.BooleanField(default=True, read_only=True)

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "sessions_count",
            "sessions_used",
            "redeem_code",
            "created_at",
            "is_active",
            "can_redeem",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
        ]


class RedeemableCenterField(BaseSerializer):
    id = serializers.UUIDField(required=True)


class ServiceField(BaseSerializer):
    id = serializers.UUIDField(required=True)
    sessions_count = serializers.IntegerField(min_value=1, required=True)


class BaseWellnessProgramSerializer(BaseModelSerializer):
    class Meta:
        model = WellnessProgram
        fields = ["id"]


class ProgramServiceSerializer(BaseModelSerializer):
    program = BaseProgramSerializer(read_only=True)
    service = BaseServiceSerializer(read_only=True)
    cancelled_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "program",
            "service",
            "sessions_count",
            "sessions_used",
            "redeem_code",
            "created_at",
            "is_active",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
        ]


class WellnessProgramDetailSerializer(BaseModelSerializer):
    profile = CustomerProfileWithCenterSerializer(
        source="program.customer_profile", read_only=True
    )
    program_type = serializers.ChoiceField(
        source="program.program_type", choices=ProgramType, read_only=True
    )
    is_complimentary = serializers.BooleanField(
        source="program.is_complimentary", read_only=True
    )
    price = serializers.DecimalField(
        source="program.price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        allow_null=True,
    )
    notes = serializers.CharField(
        source="program.notes", required=False, allow_null=True, allow_blank=True
    )
    expires_at = serializers.DateField(
        source="program.expires_at", required=False, allow_null=True
    )
    sessions_count = serializers.IntegerField(
        source="program.sessions_count", read_only=True
    )
    sessions_used = serializers.IntegerField(
        source="program.sessions_used", read_only=True
    )
    services_count = serializers.IntegerField(
        source="program.services_count", read_only=True
    )
    redeemable_centers_count = serializers.IntegerField(
        source="program.redeemable_centers_count", read_only=True
    )
    redeemable_centers = serializers.SerializerMethodField(read_only=True)
    created_by = BaseUserSerializer(source="program.created_by", read_only=True)

    # Cancellation
    cancellation_reason = serializers.CharField(
        source="program.cancellation_reason", read_only=True
    )
    cancelled_by = BaseUserSerializer(source="program.cancelled_by", read_only=True)
    cancelled_at = serializers.DateTimeField(
        source="program.cancelled_at", read_only=True
    )

    class Meta:
        model = WellnessProgram
        fields = [
            "id",
            "profile",
            "program_type",
            "is_complimentary",
            "price",
            "notes",
            "expires_at",
            "sessions_count",
            "sessions_used",
            "services_count",
            "redeemable_centers",
            "redeemable_centers_count",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
            # Cancellation
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
        ]

    def get_redeemable_centers(self, instance: WellnessProgram):
        qs = instance.program.redeemable_centers.all()[:3]
        return BaseCenterSerializer(qs, many=True, context=self.context).data

    def create(self, validated_data):
        raise serializers.ValidationError("Create not allowed.")

    def update(self, instance: WellnessProgram, validated_data):
        program_data = validated_data.pop("program", {})
        program = instance.program
        for attr, value in program_data.items():
            setattr(program, attr, value)
        program.save(update_fields=list(program_data.keys()))
        return instance


class WellnessProgramSerializer(BaseModelSerializer):
    profile = CustomerProfileWithCenterSerializer(
        source="program.customer_profile", read_only=True
    )
    profile_id = serializers.UUIDField(write_only=True, required=False)
    # center = BaseCenterSerializer(source='program.center', read_only=True)
    program_type = serializers.ChoiceField(
        source="program.program_type", choices=ProgramType, default=ProgramType.WELLNESS
    )
    notes = serializers.CharField(
        source="program.notes", required=False, allow_null=True, allow_blank=True
    )
    expires_at = serializers.DateField(source="program.expires_at", required=True)
    is_complimentary = serializers.BooleanField(
        source="program.is_complimentary", default=True
    )
    price = serializers.DecimalField(
        source="program.price",
        allow_null=True,
        required=False,
        max_digits=10,
        decimal_places=2,
    )
    sessions_count = serializers.IntegerField(
        source="program.sessions_count", default=0, read_only=True
    )
    sessions_used = serializers.IntegerField(
        source="program.sessions_used", default=0, read_only=True
    )
    services_count = serializers.IntegerField(
        source="program.services_count", default=0, read_only=True
    )
    redeemable_centers_count = serializers.IntegerField(
        source="program.redeemable_centers_count", default=0, read_only=True
    )
    redeemable_centers = serializers.SerializerMethodField(read_only=True)
    # services = serializers.SerializerMethodField(read_only=True)

    # Many to many write only fields
    add_redeemable_centers = RedeemableCenterField(many=True, write_only=True)
    add_services = ServiceField(many=True, required=True, write_only=True)

    # Read only
    created_by = BaseUserSerializer(source="program.created_by", read_only=True)

    class Meta:
        model = WellnessProgram
        fields = [
            "id",
            "profile",
            "profile_id",
            # "center",
            "program_type",
            "notes",
            "expires_at",
            "is_complimentary",
            "price",
            "services_count",
            "sessions_count",
            "sessions_used",
            "redeemable_centers",
            "redeemable_centers_count",
            # "services",
            "add_redeemable_centers",
            "add_services",
            "created_at",
            "updated_at",
            "is_active",
            "created_by",
        ]

    def get_services(self, instance: WellnessProgram):
        qs = instance.program.program_services.all()[:3]
        return BaseProgramServiceSerializer(qs, many=True, context=self.context).data

    def get_redeemable_centers(self, instance: WellnessProgram):
        qs = instance.program.redeemable_centers.all()[:3]
        return BaseCenterSerializer(qs, many=True, context=self.context).data

    @classmethod
    def get_invalid_redeemable_centers(cls, profile_id, center_ids):
        _center_ids = set(
            Center.objects.filter(
                pk__in=center_ids,
                customer_assignments__customer_profile_id=profile_id,
            ).values_list("pk", flat=True)
        )
        missing = set(center_ids) - _center_ids
        return missing

    @classmethod
    def get_invalid_services(cls, service_ids):
        _service_ids = set(
            Service.objects.filter(pk__in=service_ids).values_list("pk", flat=True)
        )
        return set(service_ids) - set(_service_ids)

    def create(self, validated_data):
        created_by = validated_data.get("created_by")
        center_id = validated_data.get("center_id")
        profile_id = validated_data.pop("profile_id")
        if not center_id:
            raise serializers.ValidationError("Invalid center ID provided")
        profile = CustomerProfile.objects.filter(pk=profile_id).first()
        if not profile:
            raise serializers.ValidationError(
                {"profile_id": "Invalid profile ID provided"}
            )
        program_data = validated_data.pop("program", {})
        add_redeemable_centers = validated_data.pop("add_redeemable_centers", [])
        add_services = validated_data.pop("add_services", [])
        is_complimentary = program_data.get("is_complimentary")
        price = program_data.get("price")
        if not is_complimentary and not price:
            raise serializers.ValidationError(
                {"price": "Price is required when program is not complimentary"}
            )

        if add_redeemable_centers:
            missing_ids = self.get_invalid_redeemable_centers(
                profile_id, [i.get("id") for i in add_redeemable_centers]
            )
            if missing_ids:
                raise serializers.ValidationError(
                    {
                        "add_redeemable_centers": f"Invalid center IDs provided: {", ".join(map(str, missing_ids))}"
                    }
                )

        if add_services:
            missing_ids = self.get_invalid_services([i.get("id") for i in add_services])
            if missing_ids:
                raise serializers.ValidationError(
                    {
                        "add_services": f'Invalid service ID provided: {", ".join(map(str, missing_ids))}'
                    }
                )

        with transaction.atomic():
            program = Program.objects.create(
                **program_data,
                customer_profile_id=profile_id,
                center_id=center_id,
                created_by=created_by,
            )
            program.redeemable_centers.add(
                *[i.get("id") for i in add_redeemable_centers]
            )
            program_services = [
                ProgramService(
                    program=program,
                    service_id=i.get("id"),
                    sessions_count=i.get("sessions_count"),
                )
                for i in add_services
            ]
            ProgramService.objects.bulk_create(program_services, ignore_conflicts=True)
            wellness_program = WellnessProgram.objects.create(program=program)
            update_program_sessions_count(program.pk)
            update_program_services_count(program.pk)
            update_program_redeemable_centers_count(program.pk)
            program.refresh_from_db(
                fields=["sessions_count", "services_count", "redeemable_centers_count"]
            )

            return wellness_program


class WellnessProgramCancelSerializer(BaseModelSerializer):
    cancellation_reason = serializers.CharField(
        source="program.cancellation_reason",
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    cancelled_by = BaseUserSerializer(source="program.cancelled_by", read_only=True)
    cancelled_at = serializers.DateTimeField(
        source="program.cancelled_at", read_only=True
    )

    class Meta:
        model = WellnessProgram
        fields = ["cancellation_reason", "cancelled_by", "cancelled_at"]

    def create(self, validated_data):
        wellness_program = validated_data.pop("wellness_program", None)
        cancelled_by = validated_data.pop("cancelled_by", None)
        program_fields = validated_data.pop("program", {})
        cancellation_reason = program_fields.get("cancellation_reason")
        if not wellness_program:
            raise serializers.ValidationError("Not valid wellness program provided")
        if not wellness_program.is_active:
            raise serializers.ValidationError("Program already cancelled")
        wellness_program.is_active = False
        wellness_program.program.is_active = False
        wellness_program.program.cancellation_reason = cancellation_reason
        wellness_program.program.cancelled_by = cancelled_by

        wellness_program.save(update_fields=["is_active"])
        wellness_program.program.save(
            update_fields=["is_active", "cancellation_reason", "cancelled_by"]
        )
        cancel_program_services(
            wellness_program.program_id,
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
        )

        return wellness_program


class WellnessProgramRedeemSerializer(BaseModelSerializer):
    center_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = WellnessProgram
        fields = ["center_id"]

    def create(self, validated_data):
        wellness_program: WellnessProgram = validated_data.pop("wellness_program")
        redeemed_by = validated_data.pop("redeemed_by")
        center_id = validated_data["center_id"]

        if not wellness_program.is_active:
            raise serializers.ValidationError("This program has been cancelled.")
        program_exists = (
            Program.objects.filter(pk=wellness_program.program.id)
            .exclude(expires_at__lt=timezone.localdate())
            .exists()
        )
        if not program_exists:
            raise serializers.ValidationError("This program has expired.")

        if not ProgramService.objects.filter(
            program=wellness_program.program,
            is_active=True,
            service__center_assignments__center_id=center_id,
            service__center_assignments__is_active=True,
        ).exists():
            raise serializers.ValidationError(
                {"center_id": "This center does not offer any service in this program."}
            )

        redeemed = redeem_all_program_services(
            wellness_program.program.id, center_id, redeemed_by
        )
        if redeemed == 0:
            raise serializers.ValidationError(
                "No sessions remaining across any service in this program."
            )

        return wellness_program


class ProgramServiceRedemptionHistorySerializer(BaseModelSerializer):
    redeem_center = MinimumCenterSerializer(read_only=True)
    redeemed_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = RedemptionHistory
        fields = [
            "id",
            "redeem_center",
            "redeemed_at",
            "quantity",
            "redeemed_by",
        ]
        read_only_fields = fields
