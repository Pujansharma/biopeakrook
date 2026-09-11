from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer, MinimumCenterSerializer
from accounts.customers.models import CustomerCenterAssignment, CustomerProfile
from accounts.customers.serializers import CustomerProfileWithCenterSerializer
from accounts.users.models import User
from accounts.users.serializers import BaseUserSerializer
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from core.utils.serializers import BaseModelSerializer, BaseSerializer
from products.serializers import BaseProductSerializer
from programs.composites.models import CompositeTemplate, CompositeTemplateService
from programs.composites.serializers import BaseCompositeTemplateSerializer
from programs.composites.utils.constants import CompositeAssessmentType
from programs.composites.utils.db import (
    create_program_service_extensions,
    update_composite_program_service_counts,
)
from programs.models import (
    CompositeProgram,
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
from programs.services.models import Service, ServiceDocument, ServiceResult
from programs.services.serializers import (
    BaseServiceDocumentModuleCategorySerializer,
    BaseServiceSerializer,
)
from programs.services.utils.constants import ServiceCategory
from programs.utils.constants import ProgramType, ServiceAssignment
from programs.utils.db import (
    update_program_redeemable_centers_count,
    update_program_services_count,
    update_program_sessions_count,
)
from programs.utils.helper import generate_program_unique_id


class CustomerTherapyProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    uid = serializers.CharField(source="program.uid", read_only=True)
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
            "uid",
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
            _associate = getattr(created_by, 'associate')
            filter_kwargs.update(
                {
                    "associate_assignments__associate": _associate,
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
            program_uid = generate_program_unique_id()
            program = Program.objects.create(
                **program_data,
                uid=program_uid,
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


class CustomerCompositeProgramCenterSerializer(BaseSerializer):
    id = serializers.UUIDField(required=True, write_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class CustomerCompositeProgramServiceFilterSerializer(BaseSerializer):
    service_category = serializers.ChoiceField(
        choices=[
            ServiceCategory.ASSESSMENT,
            ServiceCategory.THERAPY,
        ],
        required=False,
    )
    assignment_type = serializers.ChoiceField(
        choices=ServiceAssignment,
        required=False,
    )
    composite_program = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)
    active = serializers.ChoiceField(
        choices=["0", "1"],
        required=False,
    )


class CustomerCompositeProgramListReferenceSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    uid = serializers.CharField(source="program.uid", read_only=True)
    name = serializers.CharField(read_only=True, allow_null=True)
    template = BaseCompositeTemplateSerializer(
        source='composite_template', read_only=True
    )

    class Meta:
        model = CompositeProgram
        fields = ["id", "uid", "name", 'template']


class CustomerCompositeProgramServiceListSerializer(BaseModelSerializer):
    composite_program = CustomerCompositeProgramListReferenceSerializer(
        source="program.composite_program",
        read_only=True,
    )
    service = BaseServiceSerializer(read_only=True)
    assignment_type_code = serializers.CharField(
        source="assignment_type",
        read_only=True,
    )
    can_redeem = serializers.BooleanField(default=True, read_only=True)
    sessions_count = serializers.IntegerField(
        source="therapy_service.sessions_count",
        read_only=True,
        default=None,
        allow_null=True,
    )
    sessions_used = serializers.IntegerField(
        source="therapy_service.sessions_used",
        read_only=True,
        default=None,
        allow_null=True,
    )
    sessions_cancelled = serializers.IntegerField(
        source="therapy_service.sessions_cancelled",
        read_only=True,
        default=None,
        allow_null=True,
    )
    redeem_code = serializers.CharField(
        source="therapy_service.redeem_code",
        read_only=True,
        default=None,
        allow_null=True,
    )
    cancelled_by = BaseUserSerializer(read_only=True)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "composite_program",
            "service",
            "assignment_type",
            "assignment_type_code",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "redeem_code",
            "results_count",
            "documents_count",
            "reports_count",
            "raw_data_count",
            "can_redeem",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
            "created_date",
            "created_by",
            "is_active",
            "created_at",
            "updated_at",
        ]


class CustomerCompositeProgramServiceSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    service = BaseServiceSerializer(read_only=True)
    service_assignment_type = serializers.SerializerMethodField(read_only=True)
    service_assignment_type_code = serializers.CharField(
        source="assignment_type",
        read_only=True,
    )
    can_redeem = serializers.BooleanField(default=True, read_only=True)
    sessions_count = serializers.SerializerMethodField(read_only=True)
    sessions_used = serializers.SerializerMethodField(read_only=True)
    sessions_cancelled = serializers.SerializerMethodField(read_only=True)
    redeem_code = serializers.SerializerMethodField(read_only=True)
    cancellation_reason = serializers.CharField(read_only=True, allow_null=True)
    cancelled_by = BaseUserSerializer(read_only=True)
    cancelled_at = serializers.DateTimeField(read_only=True, allow_null=True)
    cancelled_date = serializers.DateField(read_only=True, allow_null=True)
    created_date = serializers.DateField(read_only=True)
    created_by = BaseUserSerializer(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "service_assignment_type",
            "service_assignment_type_code",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "redeem_code",
            "can_redeem",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
            "created_date",
            "created_by",
            "is_active",
            "created_at",
            "updated_at",
        ]

    @classmethod
    def get_service_assignment_type(
            cls,
            instance: ProgramService,
    ):
        return instance.get_assignment_type_display()

    def get_redeem_code(self, instance: ProgramService):
        therapy_program_service = getattr(instance, "therapy_service", None)
        return getattr(therapy_program_service, "redeem_code", None)

    def get_sessions_count(self, instance: ProgramService):
        therapy_program_service = getattr(instance, "therapy_service", None)
        return getattr(therapy_program_service, "sessions_count", None)

    def get_sessions_used(self, instance: ProgramService):
        therapy_program_service = getattr(instance, "therapy_service", None)
        return getattr(therapy_program_service, "sessions_used", None)

    def get_sessions_cancelled(self, instance: ProgramService):
        therapy_program_service = getattr(instance, "therapy_service", None)
        return getattr(therapy_program_service, "sessions_cancelled", None)


class CustomerCompositeProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    name = serializers.CharField(
        max_length=200,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    assessment_type = serializers.ChoiceField(
        choices=[*CompositeAssessmentType.choices],
        required=False,
        allow_null=True,
    )
    assessment_type_code = serializers.CharField(
        source="assessment_type",
        read_only=True,
        allow_null=True,
    )
    profile = CustomerProfileWithCenterSerializer(
        source="program.customer_profile",
        read_only=True,
    )
    center = MinimumCenterSerializer(source="program.center", read_only=True)
    composite_template = BaseCompositeTemplateSerializer(read_only=True)
    composite_template_id = serializers.UUIDField(write_only=True, required=True)
    uid = serializers.CharField(source='program.uid', read_only=True)
    program_type = serializers.ChoiceField(
        source="program.program_type",
        choices=[*ProgramType.choices],
        read_only=True,
    )
    notes = serializers.CharField(
        source="program.notes",
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    expires_at = serializers.DateField(source="program.expires_at", required=False)
    is_complimentary = serializers.BooleanField(
        source="program.is_complimentary",
        default=True,
    )
    price = serializers.DecimalField(
        source="program.price",
        allow_null=True,
        required=False,
        max_digits=10,
        decimal_places=2,
    )
    redeemable_centers = CustomerCompositeProgramCenterSerializer(
        source="program.redeemable_centers",
        many=True,
        required=True,
        allow_empty=False,
    )
    services = serializers.SerializerMethodField(read_only=True)
    services_count = serializers.IntegerField(
        source="program.services_count",
        read_only=True,
    )
    add_ons_count = serializers.IntegerField(read_only=True)
    assessment_services_count = serializers.IntegerField(read_only=True)
    therapy_services_count = serializers.IntegerField(read_only=True)
    consultation_services_count = serializers.IntegerField(read_only=True)
    results_count = serializers.IntegerField(read_only=True)
    documents_count = serializers.IntegerField(read_only=True)
    reports_count = serializers.IntegerField(read_only=True)
    raw_data_count = serializers.IntegerField(read_only=True)
    redeemable_centers_count = serializers.IntegerField(
        source="program.redeemable_centers_count",
        read_only=True,
    )
    cancellation_reason = serializers.CharField(
        source="program.cancellation_reason",
        read_only=True,
    )
    cancelled_by = BaseUserSerializer(
        source="program.cancelled_by",
        read_only=True,
    )
    cancelled_at = serializers.DateTimeField(
        source="program.cancelled_at",
        read_only=True,
    )
    cancelled_date = serializers.DateField(
        source="program.cancelled_date",
        read_only=True,
    )
    created_date = serializers.DateField(
        source="program.created_date",
        required=False,
    )
    is_active = serializers.BooleanField(source="program.is_active", read_only=True)
    created_at = serializers.DateTimeField(source="program.created_at", read_only=True)
    updated_at = serializers.DateTimeField(source="program.updated_at", read_only=True)
    created_by = BaseUserSerializer(source="program.created_by", read_only=True)

    class Meta:
        model = CompositeProgram
        fields = [
            "id",
            "uid",
            "name",
            "assessment_type",
            "assessment_type_code",
            "profile",
            "center",
            "composite_template",
            "composite_template_id",
            "program_type",
            "notes",
            "expires_at",
            "is_complimentary",
            "price",
            "redeemable_centers",
            "redeemable_centers_count",
            "services",
            "services_count",
            "add_ons_count",
            "assessment_services_count",
            "therapy_services_count",
            "consultation_services_count",
            "results_count",
            "documents_count",
            "reports_count",
            "raw_data_count",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
            "created_date",
            "is_active",
            "created_at",
            "updated_at",
            "created_by",
        ]

    def create(self, validated_data: dict):
        name = validated_data.get("name")
        if not name:
            validated_data["name"] = None
        customer_profile = validated_data.pop("customer_profile")
        center = validated_data.pop("center")
        created_by = validated_data.pop("created_by")
        composite_template_identifier = validated_data.pop(
            "composite_template_id"
        )
        program_data = validated_data.pop("program", {})
        redeemable_center_data = program_data.pop("redeemable_centers")
        expires_at = program_data.get("expires_at")
        is_complimentary = program_data.get("is_complimentary", True)
        price = program_data.get("price")

        if expires_at and expires_at < timezone.localdate():
            raise serializers.ValidationError(
                {"expires_at": "Expiry date cannot be earlier than today's date."}
            )
        if not is_complimentary and price is None:
            raise serializers.ValidationError(
                {"price": "Price is required when program is not complimentary."}
            )

        center_identifiers = {
            center_data["id"] for center_data in redeemable_center_data
        }
        center_assignments = CustomerCenterAssignment.objects.filter(
            customer_profile=customer_profile,
            center__pk__in=center_identifiers,
            center__is_active=True,
            is_active=True,
        ).select_related("center")

        centers_by_primary_key = {
            center_assignment.center.pk: center_assignment.center
            for center_assignment in center_assignments
        }
        invalid_center_identifiers = center_identifiers - set(
            centers_by_primary_key
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
                    "redeemable_centers": (
                        "Centers are not assigned to this customer profile: "
                        f"{invalid_identifiers}"
                    )
                }
            )
        redeemable_centers = [
            centers_by_primary_key[center_identifier]
            for center_identifier in center_identifiers
        ]

        composite_template = CompositeTemplate.objects.filter(
            pk=composite_template_identifier,
            is_active=True,
        ).first()
        if not composite_template:
            raise serializers.ValidationError(
                {"composite_template_id": "Invalid or inactive composite template."}
            )

        template_services = list(
            CompositeTemplateService.objects.filter(
                composite_template=composite_template,
                is_active=True,
                service__is_active=True,
            )
            .select_related("service")
            .order_by("created_at")
        )
        if not template_services:
            raise serializers.ValidationError(
                {"composite_template_id": "Composite template has no active services."}
            )

        has_assessment_service = any(
            template_service.service.service_category
            == ServiceCategory.ASSESSMENT
            for template_service in template_services
        )
        if has_assessment_service and not validated_data.get("assessment_type"):
            raise serializers.ValidationError(
                {
                    "assessment_type": (
                        "Assessment type is required when the composite template "
                        "contains an assessment service."
                    )
                }
            )

        with transaction.atomic():
            program_uid = generate_program_unique_id()
            program = Program.objects.create(
                **program_data,
                uid=program_uid,
                program_type=ProgramType.COMPOSITE,
                customer_profile=customer_profile,
                center=center,
                created_by=created_by,
            )
            program.redeemable_centers.add(*redeemable_centers)
            validated_data["program"] = program
            validated_data["composite_template"] = composite_template
            validated_data["template_description"] = composite_template.description
            composite_program = super().create(validated_data)
            service_quantities = [
                template_service.quantity
                for template_service in template_services
            ]
            program_services = [
                ProgramService(
                    program=program,
                    service=template_service.service,
                    created_by=created_by,
                )
                for template_service in template_services
            ]
            ProgramService.objects.bulk_create(program_services)
            create_program_service_extensions(
                program_services,
                service_quantities,
            )
            update_program_services_count(program.pk)
            update_composite_program_service_counts(program.pk)
            update_program_redeemable_centers_count(program.pk)
            composite_program.refresh_from_db(
                fields=[
                    "add_ons_count",
                    "assessment_services_count",
                    "therapy_services_count",
                    "consultation_services_count",
                ]
            )
            program.refresh_from_db(
                fields=["services_count", "redeemable_centers_count"]
            )
        return composite_program

    def get_services(self, instance: CompositeProgram):
        program_services = getattr(instance.program, "service_preview", None)
        if not program_services:
            return None
        return CustomerCompositeProgramServiceSerializer(
            program_services,
            many=True,
            context=self.context,
        ).data


class BaseCompositeProgramSerializer(BaseModelSerializer):
    id = serializers.UUIDField(source="pk", read_only=True)
    uid = serializers.CharField(source="program.uid", read_only=True)

    class Meta:
        model = CompositeProgram
        fields = [
            "id",
            "uid",
            "name",
        ]
        read_only_fields = fields


class CustomerServiceDocumentProgramServiceSerializer(BaseModelSerializer):
    service = BaseServiceSerializer(read_only=True)
    composite_program = BaseCompositeProgramSerializer(
        source="program.composite_program",
        read_only=True,
        allow_null=True,
        default=None,
    )
    composite_template = BaseCompositeTemplateSerializer(
        source="program.composite_program.composite_template",
        read_only=True,
        allow_null=True,
        default=None,
    )

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "composite_program",
            "composite_template",
        ]


class CustomerResultSerializer(BaseModelSerializer):
    program_service = CustomerServiceDocumentProgramServiceSerializer(
        read_only=True
    )
    product = BaseProductSerializer(read_only=True)
    result_mode_code = serializers.CharField(
        source="result_mode",
        read_only=True,
    )
    document_type_code = serializers.CharField(
        source="document_type",
        read_only=True,
    )

    class Meta:
        model = ServiceResult
        fields = [
            "id",
            "program_service",
            "product",
            "provider_name",
            "product_name",
            "result_mode",
            "result_mode_code",
            "document_type",
            "document_type_code",
            "documents_count",
            "sample_collection_date",
            "report_generation_date",
        ]


class CustomerServiceDocumentSerializer(
    BaseServiceDocumentModuleCategorySerializer
):
    document_category_code = serializers.CharField(
        source="document_category",
        read_only=True,
    )
    result = CustomerResultSerializer(read_only=True)

    class Meta:
        model = ServiceDocument
        fields = [
            "id",
            "result",
            "file",
            "filename",
            "content_type",
            "document_category",
            "document_category_code",
            "module_category",
            "module_category_code",
            "is_active",
            "created_at",
            "updated_at",
        ]
