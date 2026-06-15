from django.db.models import (
    Exists,
    OuterRef,
    Q,
    Prefetch,
    ProtectedError,
    RestrictedError,
)

from accounts.centers.models import Center
from accounts.centers.serializers import ServiceAvailableCenterSerializer
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseListAPIView,
)
from products.models import Product
from products.serializers import ServiceAvailableProductSerializer
from programs.models import ProgramService
from programs.services.models import (
    Service,
    CenterServiceAssignment,
    ServiceProductAssignment,
)
from programs.services.serializers import (
    ServiceSerializer,
)
from programs.services.utils.constants import ServiceCategory


class ServicesView(BaseListCreateAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active", None)
        center_ids = self.request.query_params.getlist("center_id", [])
        category_query = self.request.query_params.get("category", None)
        if category_query and category_query in ServiceCategory:
            filter_kwargs["service_category"] = category_query

        if center_ids:
            filter_kwargs["center_assignments__center_id__in"] = center_ids

        if active_query and active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))

        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        locked_subquery = ProgramService.objects.filter(service=OuterRef("pk"))
        prefetch = Prefetch(
            "center_assignments",
            queryset=CenterServiceAssignment.objects.filter(
                center__is_active=True,
            ).select_related("center"),
        )

        if center_ids:
            prefetch = Prefetch(
                "center_assignments",
                queryset=CenterServiceAssignment.objects.filter(
                    center__is_active=True, center_id__in=center_ids
                ).select_related("center"),
            )

        qs = (
            Service.objects.filter(search, **filter_kwargs)
            .annotate(is_locked=Exists(locked_subquery))
            .prefetch_related(prefetch)
            .select_related("created_by")
            .order_by("-created_at")
            .distinct()
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ServiceDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        qs = (
            Service.objects.filter()
            .prefetch_related(
                Prefetch(
                    "center_assignments",
                    queryset=CenterServiceAssignment.objects.select_related("center"),
                )
            )
            .select_related("created_by")
        )
        return qs

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError, RestrictedError:
            self.raise_bad_request(
                "This service is currently in use and cannot be deleted. Deactivate it instead."
            )


class ServiceAvailableCenters(BaseListAPIView):
    serializer_class = ServiceAvailableCenterSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        exists_subquery = CenterServiceAssignment.objects.filter(
            center_id=OuterRef("pk"), service_id=self.kwargs["pk"], is_active=True
        )
        qs = (
            Center.objects.filter(search, is_active=True)
            .annotate(exists=Exists(exists_subquery))
            .order_by("-created_at")
        )
        return qs


class ServiceAvailableProducts(BaseListAPIView):
    serializer_class = ServiceAvailableProductSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        subquery = ServiceProductAssignment.objects.filter(
            product_id=OuterRef("pk"),
            service_id=self.kwargs["pk"],
        )

        qs = (
            Product.objects.filter(search)
            .annotate(exists=Exists(subquery))
            .prefetch_related('provider')
            .order_by("-exists", "-created_at")
        )
        return qs
