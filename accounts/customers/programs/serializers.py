from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
from accounts.customers.models import CustomerProfile
from accounts.users.models import User
from accounts.users.serializers import BaseUserSerializer
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from core.utils.serializers import BaseModelSerializer
from programs.models import (
    Program,
    ProgramService,
    TherapyProgram,
    TherapyProgramService,
)
from programs.serializers import (
    BaseProgramServiceSerializer,
    RedeemableCenterField,
    ServiceField,
)
from programs.services.models import Service
from programs.utils.constants import ProgramType
from programs.utils.db import (
    update_program_redeemable_centers_count,
    update_program_services_count,
    update_program_sessions_count,
)


class CustomerTherapyProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    center_id = serializers.UUIDField(required=True, write_only=True)
    program_type = serializers.ChoiceField(
        source="program.program_type",
        choices=ProgramType,
        read_only=True,
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
        source="program.services_count", read_only=True
    )
    services = serializers.SerializerMethodField(read_only=True)
    redeemable_centers_count = serializers.IntegerField(
        source="program.redeemable_centers_count", read_only=True
    )
    redeemable_centers = serializers.SerializerMethodField(read_only=True)
    add_redeemable_centers = RedeemableCenterField(
        many=True,
        required=False,
        allow_empty=True,
        write_only=True,
    )
    add_services = ServiceField(
        many=True,
        required=True,
        allow_empty=False,
        write_only=True,
    )
    created_date = serializers.DateField(source="program.created_date", required=False)
    cancelled_date = serializers.DateField(
        source="program.cancelled_date", required=False
    )
    created_by = BaseUserSerializer(source="program.created_by", read_only=True)

    class Meta:
        model = TherapyProgram
        fields = [
            "id",
            "center_id",
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
            "services",
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
        program_services = getattr(instance.program, "service_preview", [])
        return BaseProgramServiceSerializer(
            program_services,
            many=True,
            context=self.context,
        ).data

    def get_redeemable_centers(self, instance: TherapyProgram):
        redeemable_centers = instance.program.redeemable_centers.all()[:3]
        return BaseCenterSerializer(
            redeemable_centers,
            many=True,
            context=self.context,
        ).data

    @classmethod
    def get_invalid_redeemable_centers(
        cls,
        customer_profile: CustomerProfile,
        center_identifiers: set[UUID],
    ) -> set[UUID]:
        valid_center_identifiers = set(
            Center.objects.filter(
                pk__in=center_identifiers,
                customer_assignments__customer_profile=customer_profile,
            ).values_list("pk", flat=True)
        )
        return center_identifiers - valid_center_identifiers

    @classmethod
    def get_invalid_services(
        cls,
        service_identifiers: set[UUID],
    ) -> set[UUID]:
        valid_service_identifiers = set(
            Service.objects.filter(pk__in=service_identifiers).values_list(
                "pk", flat=True
            )
        )
        return service_identifiers - valid_service_identifiers

    @classmethod
    def get_center(
        cls,
        center_identifier: UUID,
        created_by: User,
    ) -> Center | None:
        filter_kwargs = {
            "pk": center_identifier,
            "is_active": True,
        }
        if get_user_account_type(created_by) == UserType.ASSOCIATE:
            filter_kwargs.update(
                {
                    "associate_assignments__associate": created_by.associate,
                    "associate_assignments__is_active": True,
                }
            )
        return Center.objects.filter(**filter_kwargs).distinct().first()

    def create(self, validated_data: dict) -> TherapyProgram:
        customer_profile = validated_data.pop("customer_profile")
        created_by = validated_data.pop("created_by")
        center_identifier = validated_data.pop("center_id")
        program_data = validated_data.pop("program", {})
        redeemable_center_data = validated_data.pop("add_redeemable_centers", [])
        service_data = validated_data.pop("add_services")

        expires_at = program_data.get("expires_at")
        if expires_at and expires_at < timezone.localdate():
            raise serializers.ValidationError(
                {"expires_at": "Expiry date cannot be earlier than today's date."}
            )

        is_complimentary = program_data.get("is_complimentary", True)
        price = program_data.get("price")
        if not is_complimentary and price is None:
            raise serializers.ValidationError(
                {"price": "Price is required when program is not complimentary."}
            )

        center = self.get_center(center_identifier, created_by)
        if not center:
            raise serializers.ValidationError(
                {"center_id": "Invalid or unauthorized center ID provided."}
            )

        redeemable_center_identifiers = {
            center_data["id"] for center_data in redeemable_center_data
        }
        invalid_center_identifiers = self.get_invalid_redeemable_centers(
            customer_profile,
            redeemable_center_identifiers,
        )
        if invalid_center_identifiers:
            invalid_identifiers = ", ".join(
                str(center_identifier)
                for center_identifier in sorted(
                    invalid_center_identifiers,
                    key=str,
                )
            )
            raise serializers.ValidationError(
                {
                    "add_redeemable_centers": (
                        "Invalid center IDs provided: "
                        f"{invalid_identifiers}."
                    )
                }
            )

        service_identifiers = {service["id"] for service in service_data}
        invalid_service_identifiers = self.get_invalid_services(service_identifiers)
        if invalid_service_identifiers:
            invalid_identifiers = ", ".join(
                str(service_identifier)
                for service_identifier in sorted(
                    invalid_service_identifiers,
                    key=str,
                )
            )
            raise serializers.ValidationError(
                {
                    "add_services": (
                        "Invalid service IDs provided: "
                        f"{invalid_identifiers}."
                    )
                }
            )

        services = Service.objects.filter(pk__in=service_identifiers)
        services_by_primary_key = {service.pk: service for service in services}
        sessions_count_by_service_primary_key = {
            service["id"]: service["sessions_count"] for service in service_data
        }

        with transaction.atomic():
            program = Program.objects.create(
                **program_data,
                program_type=ProgramType.THERAPY,
                customer_profile=customer_profile,
                center=center,
                created_by=created_by,
            )
            program.redeemable_centers.add(*redeemable_center_identifiers)
            therapy_program = TherapyProgram.objects.create(program=program)
            program_services = [
                ProgramService(
                    program=program,
                    service=services_by_primary_key[service_identifier],
                    created_by=created_by,
                )
                for service_identifier in service_identifiers
            ]
            ProgramService.objects.bulk_create(program_services)
            TherapyProgramService.objects.bulk_create(
                [
                    TherapyProgramService(
                        program_service=program_service,
                        sessions_count=sessions_count_by_service_primary_key[
                            program_service.service.pk
                        ],
                    )
                    for program_service in program_services
                ]
            )
            update_program_sessions_count(program.pk)
            update_program_services_count(program.pk)
            update_program_redeemable_centers_count(program.pk)
            therapy_program.refresh_from_db(
                fields=["sessions_count", "sessions_used", "sessions_cancelled"]
            )
            program.refresh_from_db(
                fields=["services_count", "redeemable_centers_count"]
            )
            program.service_preview = list(
                ProgramService.objects.filter(program=program)
                .select_related("service", "created_by", "therapy_service")[:3]
            )

        return therapy_program
