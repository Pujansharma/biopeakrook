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
from programs.models import ProgramService, TherapyProgram, TherapyProgramService
from programs.serializers import (
    BaseProgramServiceSerializer,
)
from programs.services.models import CenterServiceAssignment
from programs.therapy.serializers import (
    TherapyProgramDetailSerializer,
    TherapyProgramCancelSerializer,
    TherapyProgramRedeemSerializer,
    TherapyProgramServiceSerializer,
)


class TherapyProgramServicesView(BaseListAPIView):
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


class TherapyProgramDetailView(BaseRetrieveUpdateAPIView):
    serializer_class = TherapyProgramDetailSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        qs = (
            TherapyProgram.objects.filter()
            .select_related(
                "program",
                "program__center",
                "program__created_by",
                "program__customer_profile__customer__user",
            )
            .prefetch_related(
                Prefetch(
                    "program__program_services",
                    queryset=ProgramService.objects.select_related(
                        "service", "created_by", "therapy_service"
                    ),
                ),
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


class TherapyProgramServicesListView(BaseListAPIView):
    serializer_class = BaseProgramServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        subquery_filter_kwargs = {}
        center_id = self.request.headers.get("x-center-id", None)
        if center_id:
            subquery_filter_kwargs["center_id"] = center_id
        can_redeem_subquery = CenterServiceAssignment.objects.filter(
            service=OuterRef("service"), is_active=True, **subquery_filter_kwargs
        )
        qs = (
            ProgramService.objects.filter(
                program__therapy_program__pk=self.kwargs["pk"]
            )
            .select_related(
                "cancelled_by",
                "created_by",
                "service",
                "therapy_service",
            )
            .annotate(can_redeem=Exists(can_redeem_subquery))
            .order_by("-created_at")
        )

        return qs


class TherapyProgramCancelView(BaseCreateAPIView):
    serializer_class = TherapyProgramCancelSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_therapy_program(self):
        # filter_kwargs = {}
        # user = self.request.user
        # account_type = get_user_account_type(user)
        # if account_type == UserType.ASSOCIATE:
        #     associate = getattr(user, 'associate')
        #
        qs = TherapyProgram.objects.select_related().prefetch_related().filter()
        return get_object_or_404(
            qs, "Therapy program not found with this ID", pk=self.kwargs["pk"]
        )

    def get_center(self):
        center_id = self.request.headers.get("x-center-id")
        qs = Center.objects.filter()
        return get_object_or_404(qs, "Invalid center ID provided", pk=center_id)

    def perform_create(self, serializer):
        serializer.save(
            therapy_program=self.get_therapy_program(),
            cancelled_by=self.request.user,
            center=self.get_center(),
        )


class TherapyProgramRedeemView(BaseCreateAPIView):
    serializer_class = TherapyProgramRedeemSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_therapy_program(self):
        qs = TherapyProgram.objects.select_related("program").filter()
        return get_object_or_404(
            qs, "Therapy program not found with this ID", pk=self.kwargs["pk"]
        )

    def perform_create(self, serializer):
        serializer.save(
            therapy_program=self.get_therapy_program(),
            redeemed_by=self.request.user,
        )
