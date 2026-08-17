from rest_framework.mixins import UpdateModelMixin
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from accounts.centers.models import Center
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.helper import response_format
from core.utils.views.main import (
    BaseCreateAPIView,
    BaseDestroyAPIView,
    BaseGenericAPIView,
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveAPIView,
    BaseRetrieveDestroyAPIView,
)
from products.models import Product, Provider
from products.serializers import BaseProductSerializer, BaseProviderSerializer
from programs.models import ProgramService
from programs.program_services.serializers import (
    AssessmentProgramServiceSerializer,
    AssessmentServiceDocumentSerializer,
    AssessmentServiceResultSerializer,
    ProgramServiceCancelSerializer,
    TherapyProgramServiceSerializer,
)
from programs.program_services.utils.db import (
    delete_service_document,
    delete_service_result,
)
from programs.services.models import ServiceDocument, ServiceResult
from programs.services.utils.constants import ServiceCategory


class ProgramServiceCancelViewMeta(BaseGenericAPIView):
    service_category = None
    program_service_filter_kwargs = {}

    def get_program_service_queryset(self):
        program_services = ProgramService.objects.filter(
            service__service_category=self.service_category,
            **self.program_service_filter_kwargs,
        ).select_related(
            "program",
            "service",
        )
        return program_services

    def get_program_service(self):
        return get_object_or_404(
            self.get_program_service_queryset(),
            "Program service not found.",
            pk=self.kwargs["pk"],
        )


class AssessmentProgramServiceViewMeta(BaseGenericAPIView):
    def get_assessment_program_service_queryset(self):
        program_services = ProgramService.objects.filter(
            service__service_category=ServiceCategory.ASSESSMENT,
        ).select_related("service")
        return program_services

    def get_assessment_program_service(self):
        return get_object_or_404(
            self.get_assessment_program_service_queryset(),
            "Assessment program service not found.",
            pk=self.kwargs["pk"],
        )

    def get_active_assessment_program_service(self):
        program_services = self.get_assessment_program_service_queryset().filter(
            is_active=True
        )
        return get_object_or_404(
            program_services,
            "Assessment program service not found.",
            pk=self.kwargs["pk"],
        )

    def get_service_result_queryset(self):
        service_results = (
            ServiceResult.objects.filter(
                program_service__service__service_category=(
                    ServiceCategory.ASSESSMENT
                ),
            )
            .select_related(
                "program_service",
                "program_service__service",
                "product",
                "product__provider",
                "created_by",
            )
            .prefetch_related(
                'documents'
            )

        )
        return service_results

    def get_service_document_queryset(self):
        service_documents = ServiceDocument.objects.filter(
            result__program_service__service__service_category=(
                ServiceCategory.ASSESSMENT
            ),
        ).select_related(
            "result",
            "result__program_service",
        )
        return service_documents


class AssessmentProgramServiceDetailView(BaseRetrieveAPIView):
    serializer_class = AssessmentProgramServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        program_services = (
            ProgramService.objects.filter(
                service__service_category=ServiceCategory.ASSESSMENT,
            ).select_related(
                "service",
                "created_by",
                "cancelled_by",
            )
        )
        return program_services


class AssessmentProgramServiceProviders(
    BaseListAPIView,
    AssessmentProgramServiceViewMeta,
):
    serializer_class = BaseProviderSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        program_service = self.get_active_assessment_program_service()
        providers = Provider.objects.filter(
            is_active=True,
            products__is_active=True,
            products__service_assignments__service=program_service.service,
            products__service_assignments__is_active=True,
        ).distinct()
        return providers


class AssessmentProgramServiceProducts(
    BaseListAPIView,
    AssessmentProgramServiceViewMeta,
):
    serializer_class = BaseProductSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        provider_code = self.request.query_params.get("provider", "").strip()
        if provider_code:
            filter_kwargs["provider__code"] = provider_code
        program_service = self.get_active_assessment_program_service()
        products = Product.objects.filter(
            is_active=True,
            provider__is_active=True,
            service_assignments__service=program_service.service,
            service_assignments__is_active=True,
            **filter_kwargs,
        ).select_related("provider")
        return products


class TherapyProgramServiceDetailView(BaseRetrieveAPIView):
    serializer_class = TherapyProgramServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        program_services = (
            ProgramService.objects.filter(
                service__service_category=ServiceCategory.THERAPY,
            ).select_related(
                "service",
                "therapy_service",
                "created_by",
                "cancelled_by",
            )
        )
        return program_services


class BaseProgramServiceCancelView(
    BaseCreateAPIView,
    ProgramServiceCancelViewMeta,
):
    serializer_class = ProgramServiceCancelSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def perform_create(self, serializer):
        serializer.save(
            program_service=self.get_program_service(),
            cancelled_by=self.request.user,
        )


class AssessmentProgramServiceCancelView(BaseProgramServiceCancelView):
    service_category = ServiceCategory.ASSESSMENT


class TherapyProgramServiceCancelView(BaseProgramServiceCancelView):
    service_category = ServiceCategory.THERAPY
    program_service_filter_kwargs = {"therapy_service__isnull": False}

    def get_center(self):
        center_identifier = getattr(self.request, "center_id", None)
        if not center_identifier:
            self.raise_bad_request("X-Center-ID header is required.")
        centers = Center.objects.filter()
        return get_object_or_404(
            centers,
            "Center not found with this ID.",
            pk=center_identifier,
        )

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(
            program_service=self.get_program_service(),
            cancelled_by=self.request.user,
            center=center,
        )


class ConsultationProgramServiceCancelView(BaseProgramServiceCancelView):
    service_category = ServiceCategory.CONSULTATION


class AssessmentProgramServiceResultsView(
    BaseListCreateAPIView,
    AssessmentProgramServiceViewMeta,
):
    serializer_class = AssessmentServiceResultSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        product_identifier = self.request.query_params.get("product")
        if product_identifier:
            filter_kwargs["product__pk"] = product_identifier
        program_service = self.get_assessment_program_service()
        service_results = self.get_service_result_queryset().filter(
            program_service=program_service,
            **filter_kwargs,
        ).order_by('-created_at')
        return service_results

    def perform_create(self, serializer):
        program_service = self.get_assessment_program_service()
        serializer.save(
            program_service=program_service,
            created_by=self.request.user,
        )


class AssessmentProgramServiceDocumentsView(
    BaseListAPIView,
    AssessmentProgramServiceViewMeta,
):
    serializer_class = AssessmentServiceDocumentSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        result_identifier = self.request.query_params.get("result")
        document_type = self.request.query_params.get("document_type")
        document_category = self.request.query_params.get("document_category")
        search_query = self.request.query_params.get("search", "").strip()
        if result_identifier:
            filter_kwargs["result__pk"] = result_identifier
        if document_type:
            filter_kwargs["result__document_type"] = document_type
        if document_category:
            filter_kwargs["document_category"] = document_category
        if search_query:
            filter_kwargs["filename__icontains"] = search_query
        program_service = self.get_assessment_program_service()
        service_documents = self.get_service_document_queryset().filter(
            result__program_service=program_service,
            **filter_kwargs,
        )
        return service_documents


class ServiceResultDetailView(
    BaseRetrieveDestroyAPIView,
    UpdateModelMixin,
):
    serializer_class = AssessmentServiceResultSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        service_results = (
            ServiceResult.objects.filter(
                program_service__service__service_category=(
                    ServiceCategory.ASSESSMENT
                ),
            )
            .select_related(
                "program_service",
                "program_service__service",
                "product",
                "product__provider",
                "created_by",
            )
        )
        return service_results

    def patch(self, request, *args, **kwargs):
        response = self.partial_update(request, *args, **kwargs)
        context = response_format(
            self.get_update_success_message(),
            response.data,
        )
        return Response(context, response.status_code)

    def perform_destroy(self, instance):
        delete_service_result(instance)


class ServiceResultDocumentsView(BaseListCreateAPIView):
    serializer_class = AssessmentServiceDocumentSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]
    parser_classes = [MultiPartParser, FormParser]

    def get_service_result(self):
        service_results = ServiceResult.objects.filter(
            program_service__service__service_category=(
                ServiceCategory.ASSESSMENT
            ),
        ).select_related(
            "program_service",
            "program_service__service",
        )
        return get_object_or_404(
            service_results,
            "Assessment service result not found.",
            pk=self.kwargs["pk"],
        )

    def get_queryset(self):
        filter_kwargs = {}
        document_type = self.request.query_params.get("document_type")
        document_category = self.request.query_params.get("document_category")
        search_query = self.request.query_params.get("search", "").strip()
        if document_type:
            filter_kwargs["result__document_type"] = document_type
        if document_category:
            filter_kwargs["document_category"] = document_category
        if search_query:
            filter_kwargs["filename__icontains"] = search_query
        service_result = self.get_service_result()
        service_documents = ServiceDocument.objects.filter(
            result=service_result,
            result__program_service__service__service_category=(
                ServiceCategory.ASSESSMENT
            ),
            **filter_kwargs,
        ).select_related(
            "result",
            "result__program_service",
        )
        return service_documents

    def perform_create(self, serializer):
        service_result = self.get_service_result()
        serializer.save(result=service_result)


class ServiceDocumentDeleteView(BaseDestroyAPIView):
    serializer_class = AssessmentServiceDocumentSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        service_documents = ServiceDocument.objects.filter(
            result__program_service__service__service_category=(
                ServiceCategory.ASSESSMENT
            ),
        ).select_related(
            "result",
            "result__program_service",
        )
        return service_documents

    def perform_destroy(self, instance):
        delete_service_document(instance)
