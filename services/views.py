from django.db.models import Exists, OuterRef, Q, Prefetch

from accounts.centers.models import Center
from accounts.centers.serializers import ServiceAvailableCenterSerializer
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseCreateAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseListAPIView,
)
from services.models import Service
from services.programs.models import ProgramService, RedemptionHistory
from services.programs.serializers import (
    ProgramServiceRedemptionHistorySerializer,
    ProgramServiceSerializer,
)
from services.serializers import (
    ProgramServiceCancelSerializer,
    ServiceRedeemSerializer,
    ServiceSerializer,
)


class ServicesView(BaseListCreateAPIView):
    serializer_class = ServiceSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        filter_kwargs = {}
        center_ids = self.request.query_params.getlist("center_id", [])
        if center_ids:
            filter_kwargs["centers__in"] = center_ids
        qs = (
            Service.objects.filter(**filter_kwargs)
            .prefetch_related(
                Prefetch(
                    "centers",
                    queryset=Center.objects.filter(pk__in=center_ids),
                )
            )
            .select_related("created_by")
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
            .prefetch_related("centers")
            .select_related("created_by")
        )
        return qs


class ServiceAvailableCenters(BaseListAPIView):
    serializer_class = ServiceAvailableCenterSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        exists_subquery = Center.objects.filter(
            pk=OuterRef("pk"), services__pk=self.kwargs["pk"]
        )

        qs = Center.objects.filter(search).annotate(exists=Exists(exists_subquery))
        return qs


class ProgramServicesListView(BaseListAPIView):
    serializer_class = ProgramServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        code_query_param = self.request.query_params.get("code", None)

        qs = (
            ProgramService.objects.filter(redeem_code__iexact=code_query_param)
            .select_related("cancelled_by", "program__customer_profile")
            .prefetch_related("service", "created_by", "cancelled_by")
        )
        return qs


class ServiceRedeemView(BaseCreateAPIView):
    serializer_class = ServiceRedeemSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        return ProgramService.objects.select_related(
            "program", "service", "created_by"
        ).prefetch_related("service__centers")

    def perform_create(self, serializer):
        program_service = get_object_or_404(
            self.get_queryset(),
            "Program Service not found with the given ID",
            pk=self.kwargs["pk"],
        )
        serializer.save(program_service=program_service, redeemed_by=self.request.user)


class ProgramServiceRedemptionHistory(BaseListAPIView):
    serializer_class = ProgramServiceRedemptionHistorySerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_program_service(self):
        qs = ProgramService.objects.filter()
        return get_object_or_404(qs, "Program service not found", pk=self.kwargs["pk"])

    def get_queryset(self):
        program_service = self.get_program_service()
        qs = (
            RedemptionHistory.objects.filter(program_service=program_service)
            .select_related("redeemed_by", "redeem_center")
            .prefetch_related()
        )
        return qs


class ProgramServiceCancelView(BaseCreateAPIView):
    serializer_class = ProgramServiceCancelSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_program_service(self):
        qs = ProgramService.objects.filter()
        return get_object_or_404(qs, "Program service not found", pk=self.kwargs["pk"])

    def perform_create(self, serializer):
        serializer.save(
            program_service=self.get_program_service(),
            cancelled_by=self.request.user,
        )
