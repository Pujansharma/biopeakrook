from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from accounts.users.serializers import BaseUserSerializer
from core.utils.serializers import BaseModelSerializer
from products.models import Product
from products.serializers import BaseProductSerializer
from products.utils.documents import get_allowed_document_type_choices
from programs.models import ProgramService, TherapyProgramService
from programs.program_services.utils.db import (
    update_program_service_document_counts,
    update_program_service_results_count,
    update_result_documents_count,
)
from programs.program_services.utils.helper import generate_uploaded_file_hash
from programs.services.models import ServiceDocument, ServiceResult
from programs.services.serializers import BaseServiceSerializer
from programs.services.utils.constants import (
    ServiceCategory,
    ServiceDocumentType,
    ServiceResultMode,
)
from programs.utils.db import cancel_program_service


class BaseServiceResultSerializer(BaseModelSerializer):
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
            "provider_name",
            "product_name",
            "result_mode",
            "result_mode_code",
            "document_type",
            "document_type_code",
            "sample_collection_date",
            "report_generation_date",
        ]
        read_only_fields = [
            "id",
            "provider_name",
            "product_name",
            "result_mode",
            "document_type",
            "sample_collection_date",
            "report_generation_date",
        ]


class BaseAssessmentServiceDocumentSerializer(BaseModelSerializer):
    document_category_code = serializers.CharField(source='document_category', read_only=True)

    class Meta:
        model = ServiceDocument
        fields = [
            "id",
            "file",
            "filename",
            "content_type",
            "document_category",
            "document_category_code",
        ]


class AssessmentServiceResultSerializer(BaseModelSerializer):
    product = BaseProductSerializer(read_only=True)
    product_id = serializers.UUIDField(
        required=True,
        write_only=True,
    )
    result_mode_code = serializers.CharField(
        source="result_mode",
        read_only=True,
    )
    document_type = serializers.ChoiceField(
        choices=ServiceDocumentType,
        required=True,
    )
    document_type_code = serializers.CharField(
        source="document_type",
        read_only=True,
    )
    documents_count = serializers.IntegerField(read_only=True, default=0)
    created_by = BaseUserSerializer(read_only=True)

    documents = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ServiceResult
        fields = [
            "id",
            "product",
            "product_id",
            "provider_name",
            "product_name",
            "result_mode",
            "result_mode_code",
            "document_type",
            "document_type_code",
            "sample_collection_date",
            "report_generation_date",
            "documents_count",
            'documents',
            "created_by",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "provider_name",
            "product_name",
            "result_mode",
            "documents_count",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_documents(self, instance):
        _documents = getattr(instance, 'documents', None)
        if not _documents:
            return None
        qs = _documents.all()[:3]
        return BaseAssessmentServiceDocumentSerializer(
            qs, many=True, context=self.context
        ).data

    @classmethod
    def get_assigned_product(
            cls,
            program_service: ProgramService,
            product_identifier,
    ):
        product = (
            Product.objects.filter(
                pk=product_identifier,
                is_active=True,
                provider__is_active=True,
                service_assignments__service=program_service.service,
                service_assignments__is_active=True,
            )
            .select_related("provider")
            .first()
        )
        if not product:
            raise serializers.ValidationError(
                {"product_id": "This product is not available for the service."}
            )
        return product

    @classmethod
    def _validate_document_type(cls, product: Product, document_type):
        allowed_document_types = get_allowed_document_type_choices(
            product.provider.callback,
            product.callback,
        )
        if document_type not in allowed_document_types:
            raise serializers.ValidationError(
                {
                    "document_type": (
                        "This document type is not allowed for the selected product."
                    )
                }
            )

    @classmethod
    def set_product_metadata(cls, validated_data: dict, product: Product):
        validated_data["product"] = product
        validated_data["provider_name"] = product.provider.name
        validated_data["product_name"] = product.name

    def create(self, validated_data: dict):
        program_service = validated_data.pop("program_service")
        created_by = validated_data.pop("created_by")
        product_identifier = validated_data.pop("product_id")

        with transaction.atomic():
            locked_program_service = (
                ProgramService.objects.select_for_update()
                .select_related("service")
                .filter(pk=program_service.pk)
                .first()
            )
            if not locked_program_service or not locked_program_service.is_active:
                raise serializers.ValidationError(
                    "An inactive program service cannot receive results."
                )
            product = self.get_assigned_product(
                locked_program_service,
                product_identifier,
            )
            self._validate_document_type(product, validated_data["document_type"])
            self.set_product_metadata(validated_data, product)
            validated_data["program_service"] = locked_program_service
            validated_data["created_by"] = created_by
            validated_data["result_mode"] = ServiceResultMode.UPLOAD
            service_result = super().create(validated_data)
            update_program_service_results_count(locked_program_service.pk)
        return service_result

    def update(self, instance: ServiceResult, validated_data: dict):
        product_was_provided = "product_id" in validated_data
        document_type_was_provided = "document_type" in validated_data
        product_identifier = validated_data.pop("product_id", None)

        with transaction.atomic():
            service_result = (
                ServiceResult.objects.select_for_update()
                .select_related(
                    "program_service__service",
                    "product",
                    "product__provider",
                )
                .filter(pk=instance.pk)
                .first()
            )
            product = service_result.product
            if product_was_provided:
                product = self.get_assigned_product(
                    service_result.program_service,
                    product_identifier,
                )
            document_type = validated_data.get(
                "document_type",
                service_result.document_type,
            )
            current_product_identifier = (
                service_result.product.pk if service_result.product else None
            )
            product_changed = (
                    product_was_provided and product.pk != current_product_identifier
            )
            document_type_changed = (
                    document_type_was_provided
                    and document_type != service_result.document_type
            )
            metadata_changed = product_changed or document_type_changed
            if metadata_changed and service_result.documents.exists():
                raise serializers.ValidationError(
                    "Product and document type cannot be changed after documents "
                    "have been uploaded."
                )
            if product_was_provided or document_type_was_provided:
                if not product:
                    raise serializers.ValidationError(
                        {"product_id": "A product is required for the result."}
                    )
                self._validate_document_type(product, document_type)
            if product_was_provided:
                self.set_product_metadata(validated_data, product)
            service_result = super().update(service_result, validated_data)
        return service_result


class AssessmentServiceDocumentSerializer(BaseModelSerializer):
    document_category_code = serializers.CharField(
        source="document_category",
        read_only=True,
    )

    class Meta:
        model = ServiceDocument
        fields = [
            "id",
            "file",
            "filename",
            "content_type",
            "document_category",
            "document_category_code",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "filename",
            "content_type",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data: dict):
        service_result = validated_data.pop("result")
        uploaded_file = validated_data.get("file")
        program_service_identifier = service_result.program_service.pk

        with transaction.atomic():
            program_service = (
                ProgramService.objects.select_for_update()
                .filter(pk=program_service_identifier)
                .first()
            )
            locked_service_result = (
                ServiceResult.objects.select_for_update()
                .filter(pk=service_result.pk)
                .first()
            )
            if not program_service or not program_service.is_active:
                raise serializers.ValidationError(
                    "An inactive program service cannot receive documents."
                )
            if not locked_service_result or not locked_service_result.is_active:
                raise serializers.ValidationError(
                    "An inactive result cannot receive documents."
                )
            validated_data["result"] = locked_service_result
            validated_data["filename"] = Path(uploaded_file.name).name
            validated_data["content_type"] = (
                    uploaded_file.content_type or "application/octet-stream"
            )
            validated_data["file_hash"] = generate_uploaded_file_hash(uploaded_file)
            service_document = super().create(validated_data)
            update_result_documents_count(locked_service_result.pk)
            update_program_service_document_counts(program_service.pk)
        return service_document


class ProgramServiceCancelSerializer(BaseModelSerializer):
    cancellation_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    cancelled_by = BaseUserSerializer(read_only=True)
    cancelled_at = serializers.DateTimeField(read_only=True)
    cancelled_date = serializers.DateField(
        required=False,
        default=timezone.localdate,
    )

    class Meta:
        model = ProgramService
        fields = [
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
        ]

    def create(self, validated_data: dict):
        program_service = validated_data.pop("program_service")
        cancelled_by = validated_data.pop("cancelled_by")
        center = validated_data.pop("center", None)
        if not program_service.is_active:
            raise serializers.ValidationError("Program service is already cancelled.")

        if program_service.service.service_category == ServiceCategory.THERAPY:
            therapy_program_service = (
                TherapyProgramService.objects.filter(program_service=program_service)
                .select_related("program_service")
                .first()
            )
            if therapy_program_service and (
                therapy_program_service.sessions_used
                >= therapy_program_service.sessions_count
            ):
                raise serializers.ValidationError(
                    "Service cannot be cancelled since it is already used"
                )

        cancel_program_service(
            program_service.pk,
            program_service.program.pk,
            center_id=center.pk if center else None,
            cancelled_by=cancelled_by,
            cancellation_reason=validated_data.get("cancellation_reason"),
            cancelled_date=validated_data.get("cancelled_date"),
        )
        program_service.refresh_from_db(
            fields=[
                "is_active",
                "cancellation_reason",
                "cancelled_by",
                "cancelled_at",
                "cancelled_date",
            ]
        )
        return program_service


class AssessmentProgramServiceSerializer(BaseModelSerializer):
    service = BaseServiceSerializer(read_only=True)
    assignment_type_code = serializers.CharField(
        source="assignment_type",
        read_only=True,
    )
    cancelled_by = BaseUserSerializer(read_only=True)
    created_by = BaseUserSerializer(read_only=True)

    class Meta:
        model = ProgramService
        fields = [
            "id",
            "service",
            "assignment_type",
            "assignment_type_code",
            "results_count",
            "documents_count",
            "reports_count",
            "raw_data_count",
            "created_date",
            "created_by",
            "is_active",
            "created_at",
            "updated_at",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
        ]
        read_only_fields = [
            "id",
            "assignment_type",
            "results_count",
            "documents_count",
            "reports_count",
            "raw_data_count",
            "created_date",
            "is_active",
            "created_at",
            "updated_at",
            "cancellation_reason",
            "cancelled_at",
            "cancelled_date",
        ]


class TherapyProgramServiceSerializer(BaseModelSerializer):
    service = BaseServiceSerializer(read_only=True)
    assignment_type_code = serializers.CharField(
        source="assignment_type",
        read_only=True,
    )
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
            "service",
            "assignment_type",
            "assignment_type_code",
            "sessions_count",
            "sessions_used",
            "sessions_cancelled",
            "redeem_code",
            "created_date",
            "created_by",
            "is_active",
            "created_at",
            "updated_at",
            "cancellation_reason",
            "cancelled_by",
            "cancelled_at",
            "cancelled_date",
        ]
        read_only_fields = [
            "id",
            "assignment_type",
            "created_date",
            "is_active",
            "created_at",
            "updated_at",
            "cancellation_reason",
            "cancelled_at",
            "cancelled_date",
        ]
