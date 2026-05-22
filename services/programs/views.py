from django.db.models import Prefetch, OuterRef, Exists

from accounts.centers.models import Center
from accounts.customers.models import CustomerCenterAssignment
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListAPIView,
    BaseRetrieveUpdateAPIView,
    BaseCreateAPIView,
)
from services.models import CenterServiceAssignment
from services.programs.models import ProgramService, WellnessProgram
from services.programs.serializers import (
    BaseProgramServiceSerializer,
    WellnessProgramDetailSerializer,
    WellnessProgramCancelSerializer,
    WellnessProgramRedeemSerializer,
)


class WellnessProgramDetailView(BaseRetrieveUpdateAPIView):
    serializer_class = WellnessProgramDetailSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        qs = (
            WellnessProgram.objects.filter()
            .select_related(
                "program",
                "program__center",
                "program__created_by",
                "program__customer_profile__customer__user",
            )
            .prefetch_related(
                "program__program_services",
                "program__program_services__service",
                "program__program_services__created_by",
                "program__redeemable_centers",
                Prefetch(
                    "program__customer_profile__center_assignments",
                    queryset=CustomerCenterAssignment.objects.filter(
                        is_primary=True
                    ).select_related("center"),
                    to_attr="primary_center_assignments",
                ),
            )
        )
        return qs


class WellnessProgramServicesListView(BaseListAPIView):
    serializer_class = BaseProgramServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        subquery_filter_kwargs = {}
        center_id = self.request.headers.get("x-center-id", None)
        if center_id:
            subquery_filter_kwargs["center_id"] = center_id
        can_redeem_subquery = CenterServiceAssignment.objects.filter(
            service_id=OuterRef("service_id"), is_active=True, **subquery_filter_kwargs
        )
        qs = (
            ProgramService.objects.filter(
                program__wellness_program__id=self.kwargs["pk"]
            )
            .select_related(
                "cancelled_by",
            )
            .prefetch_related("service", "created_by")
            .annotate(can_redeem=Exists(can_redeem_subquery))
            .order_by("-created_at")
        )

        return qs


class WellnessProgramCancelView(BaseCreateAPIView):
    serializer_class = WellnessProgramCancelSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_wellness_program(self):
        qs = WellnessProgram.objects.select_related().prefetch_related().filter()
        return get_object_or_404(
            qs, "Wellness program not found with this ID", pk=self.kwargs["pk"]
        )

    def get_center(self):
        center_id = self.request.headers.get("x-center-id")
        qs = Center.objects.filter()
        return get_object_or_404(qs, "Invalid center ID provided", pk=center_id)

    def perform_create(self, serializer):
        serializer.save(
            wellness_program=self.get_wellness_program(),
            cancelled_by=self.request.user,
            center=self.get_center(),
        )


class WellnessProgramRedeemView(BaseCreateAPIView):
    serializer_class = WellnessProgramRedeemSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_wellness_program(self):
        qs = WellnessProgram.objects.select_related("program").filter()
        return get_object_or_404(
            qs, "Wellness program not found with this ID", pk=self.kwargs["pk"]
        )

    def perform_create(self, serializer):
        serializer.save(
            wellness_program=self.get_wellness_program(),
            redeemed_by=self.request.user,
        )
