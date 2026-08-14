from django.db.models import ProtectedError, Q, RestrictedError

from accounts.centers.models import Center
from accounts.centers.serializers import BaseCenterSerializer
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
)
from products.models import Product
from programs.services.assessment.serializers import (
    AssessmentServiceDetailSerializer,
    AssessmentServiceProductSerializer,
    AssessmentServiceSerializer,
)
from programs.services.models import Service
from programs.services.utils.constants import ServiceCategory


class AssessmentServiceListView(BaseListCreateAPIView):
    serializer_class = AssessmentServiceSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_query = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active", None)
        if search_query:
            search |= Q(name__istartswith=search_query)
            search |= Q(name__icontains=search_query)
        if active_query and active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))

        qs = (
            Service.objects.filter(
                search, service_category=ServiceCategory.ASSESSMENT, **filter_kwargs
            )
            .prefetch_related(
                "center_assignments__center",
                "center_assignments__center__created_by",
                "product_assignments__product",
                "product_assignments__product__created_by",
            )
            .select_related("created_by")
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user, service_category=ServiceCategory.ASSESSMENT
        )


class AssessmentServiceDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = AssessmentServiceDetailSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        qs = (
            Service.objects.filter(
                service_category=ServiceCategory.ASSESSMENT,
            )
            .prefetch_related(
                "center_assignments__center",
                "center_assignments__center__created_by",
            )
            .select_related("created_by")
        )
        return qs

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError, RestrictedError:
            self.raise_bad_request("This service cannot be deleted")


class AssessmentServiceCentersView(BaseListAPIView):
    serializer_class = BaseCenterSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_assessment_service(self):
        qs = Service.objects.filter(service_category=ServiceCategory.ASSESSMENT)

        return get_object_or_404(
            qs, "Assessment service not found", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        service = self.get_assessment_service()
        search_query = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active", None)
        if search_query:
            search |= Q(name__istartswith=search_query)
            search |= Q(name__icontains=search_query)
        if active_query and active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))
        qs = Center.objects.filter(
            search, service_assignments__service=service, **filter_kwargs
        ).prefetch_related("created_by")
        return qs


class AssessmentServiceProductsView(BaseListAPIView):
    serializer_class = AssessmentServiceProductSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_assessment_service(self):
        assessment_services = Service.objects.filter(
            service_category=ServiceCategory.ASSESSMENT
        )
        return get_object_or_404(
            assessment_services,
            "Assessment service not found",
            pk=self.kwargs.get("pk"),
        )

    def get_queryset(self):
        assessment_service = self.get_assessment_service()
        return Product.objects.filter(
            service_assignments__service=assessment_service
        ).select_related("provider")
