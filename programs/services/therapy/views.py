from django.db.models import Prefetch, Q

from accounts.centers.models import Center
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseCreateAPIView,
    BaseListAPIView,
    BaseListCreateAPIView,
)
from programs.models import RedemptionHistory, TherapyProgramService
from programs.serializers import (
    ProgramServiceRedemptionHistorySerializer,
)
from programs.services.models import CenterServiceAssignment, Service
from programs.services.utils.constants import ServiceCategory
from programs.therapy.serializers import (
    TherapyProgramServiceSerializer,
)
from programs.services.therapy.serializers import TherapyServiceSerializer, TherapyServiceRedeemSerializer, \
    TherapyProgramServiceCancelSerializer


class TherapyProgramServicesListView(BaseListAPIView):
    serializer_class = TherapyProgramServiceSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        code_query_param = self.request.query_params.get("code", None)
        qs = TherapyProgramService.objects.filter(
            redeem_code__iexact=code_query_param
        ).select_related(
            "program_service",
            "program_service__cancelled_by",
            "program_service__created_by",
            "program_service__program__customer_profile",
            "program_service__service",
        )
        return qs


class TherapyServicesListView(BaseListCreateAPIView):
    serializer_class = TherapyServiceSerializer
    permission_classes = [IsAdminUser]

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
                search, service_category=ServiceCategory.THERAPY, **filter_kwargs
            )
            .prefetch_related(
                "center_assignments__center", "center_assignments__center__created_by"
            )
            .select_related("created_by")
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user, service_category=ServiceCategory.THERAPY
        )


class TherapyServiceRedeemView(BaseCreateAPIView):
    serializer_class = TherapyServiceRedeemSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        return TherapyProgramService.objects.select_related(
            "program_service",
            "program_service__program",
            "program_service__service",
            "program_service__created_by",
        ).prefetch_related(
            Prefetch(
                "program_service__service__center_assignments",
                queryset=CenterServiceAssignment.objects.filter(
                    is_active=True
                ).select_related("center"),
            )
        )

    def perform_create(self, serializer):
        therapy_program_service = get_object_or_404(
            self.get_queryset(),
            "Program Service not found with the given ID",
            pk=self.kwargs["pk"],
        )
        serializer.save(
            therapy_program_service=therapy_program_service,
            redeemed_by=self.request.user,
        )


class ProgramServiceRedemptionHistory(BaseListAPIView):
    serializer_class = ProgramServiceRedemptionHistorySerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_therapy_program_service(self):
        qs = TherapyProgramService.objects.select_related("program_service").filter()
        return get_object_or_404(
            qs, "Therapy program service not found", pk=self.kwargs["pk"]
        )

    def get_queryset(self):
        therapy_program_service = self.get_therapy_program_service()
        qs = (
            RedemptionHistory.objects.filter(
                therapy_program_service=therapy_program_service
            )
            .select_related("redeemed_by", "redeem_center")
            .prefetch_related()
        )
        return qs


class ProgramServiceCancelView(BaseCreateAPIView):
    serializer_class = TherapyProgramServiceCancelSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_therapy_program_service(self):
        qs = TherapyProgramService.objects.select_related("program_service").filter()
        return get_object_or_404(
            qs, "Therapy program service not found", pk=self.kwargs["pk"]
        )

    def get_center(self):
        center_id = self.request.headers.get("x-center-id")
        qs = Center.objects.filter()
        return get_object_or_404(qs, "Invalid center ID provided", pk=center_id)

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(
            therapy_program_service=self.get_therapy_program_service(),
            cancelled_by=self.request.user,
            center=center,
        )
