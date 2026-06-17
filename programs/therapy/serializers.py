from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer, MinimumCenterSerializer
from accounts.customers.models import CustomerProfile
from accounts.customers.serializers import CustomerProfileWithCenterSerializer
from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer
from programs.models import (
    Program,
    ProgramService,
    TherapyProgram,
    TherapyProgramService,
)
from programs.serializers import (
    BaseProgramSerializer,
    BaseProgramServiceSerializer,
    RedeemableCenterField,
    ServiceField,
)
from programs.services.models import Service
from programs.services.serializers import BaseServiceSerializer
from programs.services.utils.db import (
    redeem_all_program_services,
)
from programs.utils.constants import ProgramType
from programs.utils.db import (
    cancel_all_program_services,
    update_program_redeemable_centers_count,
    update_program_services_count,
    update_program_sessions_count,
)


class BaseTherapyProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)

    class Meta:
        model = TherapyProgram
        fields = ["id"]


class TherapyProgramServiceSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="program_service.id", read_only=True)
    program = BaseProgramSerializer(source="program_service.program", read_only=True)
    service = BaseServiceSerializer(source="program_service.service", read_only=True)
    cancelled_by = BaseUserSerializer(
        source="program_service.cancelled_by", read_only=True
    )
    cancellation_reason = serializers.CharField(
        source="program_service.cancellation_reason", read_only=True
    )
    cancelled_at = serializers.DateTimeField(
        source="program_service.cancelled_at", read_only=True
    )
    cancelled_date = serializers.DateField(
        source="program_service.cancelled_date", read_only=True
    )
    created_date = serializers.DateField(
        source="program_service.created_date", read_only=True
    )

    class Meta:
        model = TherapyProgramService
        fields = [
            "id",
            "program",
            "service",
            "sessions_count",
            "sessions_used",
            "redeem_code",
            "created_date",
            "created_at",
            "is_active",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
        ]
        read_only_fields = [
            "sessions_count",
            "sessions_used",
            "redeem_code",
        ]

    def create(self, validated_data):
        raise serializers.ValidationError("Create not allowed.")

    def update(self, instance: TherapyProgramService, validated_data):
        program_service_data = validated_data.pop("program_service", {})
        program_service = instance.program_service
        for attr, value in program_service_data.items():
            setattr(program_service, attr, value)
        if program_service_data:
            program_service.save(update_fields=list(program_service_data.keys()))
        return super().update(instance, validated_data)


class TherapyProgramDetailSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
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
    cancelled_date = serializers.DateField(source="program.cancelled_date")
    created_date = serializers.DateField(source="program.created_date")

    class Meta:
        model = TherapyProgram
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
            "sessions_cancelled",
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
            "created_date",
            "cancelled_date",
        ]

    def get_redeemable_centers(self, instance: TherapyProgram):
        qs = instance.program.redeemable_centers.all()[:3]
        return MinimumCenterSerializer(qs, many=True, context=self.context).data

    def create(self, validated_data):
        raise serializers.ValidationError("Create not allowed.")

    def update(self, instance: TherapyProgram, validated_data):
        program_data = validated_data.pop("program", {})
        program = instance.program
        for attr, value in program_data.items():
            setattr(program, attr, value)
        program.save(update_fields=list(program_data.keys()))
        return instance


class TherapyProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    profile = CustomerProfileWithCenterSerializer(
        source="program.customer_profile", read_only=True
    )
    profile_id = serializers.UUIDField(write_only=True, required=False)
    # center = BaseCenterSerializer(source='program.center', read_only=True)
    program_type = serializers.ChoiceField(
        source="program.program_type", choices=ProgramType, default=ProgramType.THERAPY
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

    # Dates
    created_date = serializers.DateField(source="program.created_date", required=False)
    cancelled_date = serializers.DateField(
        source="program.cancelled_date", required=False
    )

    # Read only
    created_by = BaseUserSerializer(source="program.created_by", read_only=True)

    class Meta:
        model = TherapyProgram
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
            "sessions_cancelled",
            "sessions_used",
            "redeemable_centers",
            "redeemable_centers_count",
            # "services",
            "add_redeemable_centers",
            "add_services",
            "created_date",
            "cancelled_date",
            "created_at",
            "updated_at",
            "is_active",
            "created_by",
        ]

    def get_services(self, instance: TherapyProgram):
        qs = instance.program.program_services.all()[:3]
        return BaseProgramServiceSerializer(qs, many=True, context=self.context).data

    def get_redeemable_centers(self, instance: TherapyProgram):
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
        expires_at = program_data.get("expires_at")

        if expires_at and expires_at < timezone.localdate():
            raise serializers.ValidationError(
                {"expires_at": "Expiry date cannot be earlier than today's date"}
            )

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
            center = Center.objects.filter(pk=center_id).first()
            if not center:
                raise serializers.ValidationError("Invalid center ID provided")

            service_ids = [service_data.get("id") for service_data in add_services]
            services = Service.objects.filter(pk__in=service_ids)
            services_by_pk = {service.pk: service for service in services}
            sessions_count_by_service_pk = {
                service_data.get("id"): service_data.get("sessions_count")
                for service_data in add_services
            }
            program = Program.objects.create(
                **program_data,
                customer_profile=profile,
                center=center,
                created_by=created_by,
            )
            program.redeemable_centers.add(
                *[
                    redeemable_center.get("id")
                    for redeemable_center in add_redeemable_centers
                ]
            )
            program_services = [
                ProgramService(
                    program=program,
                    service=services_by_pk[service_data.get("id")],
                    created_by=created_by,
                )
                for service_data in add_services
            ]
            ProgramService.objects.bulk_create(program_services, ignore_conflicts=True)
            program_services = ProgramService.objects.filter(
                program=program, service__pk__in=service_ids
            ).select_related("service")
            therapy_program_services = [
                TherapyProgramService(
                    program_service=program_service,
                    sessions_count=sessions_count_by_service_pk[
                        program_service.service.pk
                    ],
                )
                for program_service in program_services
            ]
            TherapyProgramService.objects.bulk_create(
                therapy_program_services, ignore_conflicts=True
            )
            therapy_program = TherapyProgram.objects.create(program=program)
            update_program_sessions_count(program.pk)
            update_program_services_count(program.pk)
            update_program_redeemable_centers_count(program.pk)
            therapy_program.refresh_from_db(
                fields=["sessions_count", "sessions_used", "sessions_cancelled"]
            )
            program.refresh_from_db(
                fields=["services_count", "redeemable_centers_count"]
            )

            return therapy_program


class TherapyProgramCancelSerializer(BaseModelSerializer):
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
    cancelled_date = serializers.DateField(
        source="program.cancelled_date", required=False, default=timezone.localdate()
    )

    class Meta:
        model = TherapyProgram
        fields = [
            "cancellation_reason",
            "cancelled_by",
            "cancelled_date",
            "cancelled_at",
        ]

    def create(self, validated_data):
        center = validated_data.pop("center")
        therapy_program = validated_data.pop("therapy_program", None)
        cancelled_by = validated_data.pop("cancelled_by", None)
        program_fields = validated_data.pop("program", {})
        cancellation_reason = program_fields.get("cancellation_reason")
        cancelled_date = program_fields.get("cancelled_date")
        if not therapy_program:
            raise serializers.ValidationError("Not valid therapy program provided")
        if not therapy_program.is_active:
            raise serializers.ValidationError("Program already cancelled")
        therapy_program.is_active = False
        therapy_program.program.is_active = False
        therapy_program.program.cancellation_reason = cancellation_reason
        therapy_program.program.cancelled_by = cancelled_by
        therapy_program.program.cancelled_date = cancelled_date
        therapy_program.save(update_fields=["is_active"])
        therapy_program.program.save(
            update_fields=[
                "is_active",
                "cancellation_reason",
                "cancelled_by",
                "cancelled_date",
            ]
        )
        cancel_all_program_services(
            therapy_program.program.pk,
            center_id=center.pk,
            cancelled_by=cancelled_by,
            cancellation_reason=cancellation_reason,
            cancelled_date=cancelled_date,
        )

        return therapy_program


class TherapyProgramRedeemSerializer(BaseModelSerializer):
    center_id = serializers.UUIDField(write_only=True)
    redeemed_date = serializers.DateField(required=False, default=timezone.localdate())

    class Meta:
        model = TherapyProgram
        fields = ["center_id", "redeemed_date"]

    def create(self, validated_data):
        therapy_program: TherapyProgram = validated_data.pop("therapy_program")
        redeemed_by = validated_data.pop("redeemed_by")
        center_id = validated_data["center_id"]
        redeemed_date = validated_data["redeemed_date"]
        if not therapy_program.is_active:
            raise serializers.ValidationError("This program has been cancelled.")
        program_exists = (
            Program.objects.filter(pk=therapy_program.program.pk)
            .exclude(expires_at__lt=timezone.localdate())
            .exists()
        )
        if not program_exists:
            raise serializers.ValidationError("This program has expired.")

        if not ProgramService.objects.filter(
            program=therapy_program.program,
            is_active=True,
            service__center_assignments__center_id=center_id,
            service__center_assignments__is_active=True,
        ).exists():
            raise serializers.ValidationError(
                {"center_id": "This center does not offer any service in this program."}
            )

        redeemed = redeem_all_program_services(
            therapy_program.program.pk, center_id, redeemed_by, redeemed_date
        )
        if redeemed == 0:
            raise serializers.ValidationError(
                "No sessions remaining across any service in this program."
            )

        return therapy_program
