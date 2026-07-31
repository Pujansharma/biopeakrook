from django.db.models import (
    BooleanField,
    ExpressionWrapper,
    F,
    Prefetch,
    Q,
    QuerySet,
)
from django.utils import timezone

from accounts.customers.models import CustomerProfile
from accounts.customers.programs.serializers import (
    CustomerTherapyProgramSerializer,
)
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import BaseGenericAPIView, BaseListCreateAPIView
from programs.models import ProgramService, TherapyProgram


class CustomerProgramViewMeta(BaseGenericAPIView):
    @classmethod
    def get_therapy_program_queryset(cls) -> QuerySet[TherapyProgram]:
        service_preview = ProgramService.objects.select_related(
            "service",
            "created_by",
            "therapy_service",
        )[:3]
        return (
            TherapyProgram.objects.select_related(
                "program",
                "program__created_by",
            )
            .prefetch_related(
                Prefetch(
                    "program__program_services",
                    queryset=service_preview,
                    to_attr="service_preview",
                ),
                "program__redeemable_centers",
            )
        )

    def get_customer_profile(self) -> CustomerProfile:
        filter_kwargs = {}
        user = self.request.user
        if get_user_account_type(user) == UserType.CUSTOMER:
            filter_kwargs["customer"] = user.customer
        customer_profiles = CustomerProfile.objects.filter(**filter_kwargs)
        return get_object_or_404(
            customer_profiles,
            "Customer profile with this ID not found.",
            pk=self.kwargs["pk"],
        )


class CustomerTherapyProgramsView(
    BaseListCreateAPIView,
    CustomerProgramViewMeta,
):
    permission_classes = [IsAdminUser | IsAssociateUser | (IsCustomerUser & ReadOnly)]
    serializer_class = CustomerTherapyProgramSerializer

    def get_queryset(self) -> QuerySet[TherapyProgram]:
        filter_kwargs = {}
        active_query = self.request.query_params.get("active")
        complete_query = self.request.query_params.get("complete")
        expired_query = self.request.query_params.get("expired")

        if active_query in {"0", "1"}:
            filter_kwargs["is_active"] = bool(int(active_query))
        if complete_query in {"0", "1"}:
            filter_kwargs["is_complete"] = bool(int(complete_query))

        expired_filters = {
            "1": {"program__expires_at__lt": timezone.localdate()},
            "0": {"program__expires_at__gte": timezone.localdate()},
        }
        if expired_query in expired_filters:
            filter_kwargs.update(expired_filters[expired_query])

        return (
            self.get_therapy_program_queryset()
            .annotate(
                is_complete=ExpressionWrapper(
                    Q(sessions_count=F("sessions_used") + F("sessions_cancelled")),
                    output_field=BooleanField(),
                )
            )
            .filter(
                program__customer_profile=self.get_customer_profile(),
                **filter_kwargs,
            )
        )

    def perform_create(
        self,
        serializer: CustomerTherapyProgramSerializer,
    ) -> None:
        serializer.save(
            customer_profile=self.get_customer_profile(),
            created_by=self.request.user,
        )
