from django.db.models import (
    BooleanField,
    Count,
    ExpressionWrapper,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum, FilteredRelation, Value,
)
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone

from accounts.customers.models import Customer, CustomerProfile, CustomerAssociateAssignment
from core.utils.exceptions import get_object_or_404
from core.utils.formatters import PhoneNumberFormat
from core.utils.views.main import BaseListAPIView, BaseRetrieveAPIView
from external.serializers import (
    CustomerProfileSummarySerializer,
    ExternalProgramServiceSerializer,
    CustomerWellnessProgramSerializer,
    CustomerWellnessProgramDetailSerializer,
    CustomerServiceDetailSerializer, ExternalCustomerAssociateSerializer,
)
from services.models import CenterServiceAssignment
from services.programs.models import (
    Program,
    ProgramService,
    RedemptionHistory,
    WellnessProgram,
)
from services.programs.serializers import ProgramServiceRedemptionHistorySerializer


class ExternalUserProgramView(BaseListAPIView):
    serializer_class = CustomerWellnessProgramSerializer

    def get_queryset(self):
        filter_kwargs = {}
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query, region=None)
        phone_cleaned = phone_formatter.clean(raise_exception=False)
        active_query = self.request.query_params.get("active", None)
        complete_query = self.request.query_params.get("complete", None)
        expired_query = self.request.query_params.get("expired", None)

        if active_query and active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))

        if complete_query and complete_query in ["0", "1"]:
            filter_kwargs["is_complete"] = bool(int(complete_query))

        expired_filter_map = {
            "1": {"program__expires_at__lt": timezone.localdate()},
            "0": {"program__expires_at__gte": timezone.localdate()},
        }
        if expired_query and expired_query in expired_filter_map:
            filter_kwargs.update(expired_filter_map[expired_query])

        qs = (
            WellnessProgram.objects.annotate(
                is_complete=ExpressionWrapper(
                    Q(
                        program__sessions_count=F("program__sessions_used")
                        + F("program__sessions_cancelled")
                    ),
                    output_field=BooleanField(),
                )
            )
            .filter(
                program__customer_profile__customer__user__phone=phone_cleaned,
                **filter_kwargs,
            )
            .select_related(
                "program",
            )
            .prefetch_related()
        )
        return qs


class ExternalUserProgramSummaryView(BaseRetrieveAPIView):
    serializer_class = CustomerProfileSummarySerializer

    def get_customer_profile(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_cleaned = PhoneNumberFormat(phone_query).clean(raise_exception=False)
        customer = Customer.objects.filter(user__phone=phone_cleaned).first()
        return get_object_or_404(
            CustomerProfile.objects.filter(customer=customer),
            "Customer profile not found",
        )

    def get_queryset(self):
        customer_profile = self.get_customer_profile()
        programs_base = Program.objects.filter(customer_profile=OuterRef("pk")).values(
            "customer_profile"
        )
        return CustomerProfile.objects.filter(pk=customer_profile.pk).annotate(
            programs_count=Coalesce(
                Subquery(programs_base.annotate(n=Count("pk")).values("n")[:1]),
                0,
            ),
            programs_expired=Coalesce(
                Subquery(
                    programs_base.filter(expires_at__lt=timezone.localdate())
                    .annotate(n=Count("pk"))
                    .values("n")[:1]
                ),
                0,
            ),
            programs_inactive=Coalesce(
                Subquery(
                    programs_base.filter(is_active=False)
                    .annotate(n=Count("pk"))
                    .values("n")[:1]
                ),
                0,
            ),
            sessions_count=Coalesce(
                Subquery(
                    programs_base.annotate(total=Sum("sessions_count")).values("total")[
                        :1
                    ]
                ),
                0,
            ),
            sessions_used=Coalesce(
                Subquery(
                    programs_base.annotate(total=Sum("sessions_used")).values("total")[
                        :1
                    ]
                ),
                0,
            ),
            sessions_cancelled=Coalesce(
                Subquery(
                    programs_base.annotate(total=Sum("sessions_cancelled")).values(
                        "total"
                    )[:1]
                ),
                0,
            ),
            sessions_expired=Coalesce(
                Subquery(
                    programs_base.filter(expires_at__lt=timezone.localdate())
                    .annotate(total=Sum(F("sessions_count") - F("sessions_used")))
                    .values("total")[:1]
                ),
                0,
            ),
            programs_complete=Coalesce(
                Subquery(
                    programs_base.filter(
                        is_active=True,
                        sessions_count=F("sessions_used") + F("sessions_cancelled"),
                    )
                    .annotate(count=Count("pk"))
                    .values("count")[:1]
                ),
                0,
            ),
        )

    def get_object(self):
        return self.get_queryset().first()


class ExternalUserProgramDetailView(BaseRetrieveAPIView):
    serializer_class = CustomerWellnessProgramDetailSerializer

    def get_queryset(self):
        phone_query = self.request.query_params.get("phone", None)

        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)

        return (
            WellnessProgram.objects.filter(
                program__customer_profile__customer__user__phone=phone_cleaned,
            )
            .select_related(
                "program",
            )
            .prefetch_related(
                "program__program_services",
                "program__program_services__service",
            )
        )


class ExternalUserProgramServicesListView(BaseListAPIView):
    serializer_class = ExternalProgramServiceSerializer

    def get_queryset(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)
        return (
            ProgramService.objects.filter(
                program__wellness_program__id=self.kwargs["pk"],
                program__customer_profile__customer__user__phone=phone_cleaned,
            )
            .select_related("cancelled_by")
            .prefetch_related(
                Prefetch(
                    "service__center_assignments",
                    queryset=CenterServiceAssignment.objects.filter(
                        center__redeemable_programs__wellness_program__id=self.kwargs[
                            "pk"
                        ],
                        is_active=True,
                    ).select_related("center"),
                ),
                "created_by",
            )
        )


class ExternalUserProgramServiceRedemptionHistory(BaseListAPIView):
    serializer_class = ProgramServiceRedemptionHistorySerializer

    def get_program_service(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_cleaned = PhoneNumberFormat(phone_query).clean(raise_exception=False)
        qs = ProgramService.objects.filter(
            program__customer_profile__customer__user__phone=phone_cleaned,
        ).select_related("program__customer_profile__customer__user")
        return get_object_or_404(qs, "Program service not found", pk=self.kwargs["pk"])

    def get_queryset(self):
        program_service = self.get_program_service()
        return RedemptionHistory.objects.filter(
            program_service=program_service
        ).select_related("redeemed_by", "redeem_center")


class ExternalUserProgramServiceDetailView(BaseRetrieveAPIView):
    serializer_class = CustomerServiceDetailSerializer

    def get_queryset(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)
        qs = (
            ProgramService.objects.filter(
                program__customer_profile__customer__user__phone=phone_cleaned,
            )
            .select_related("cancelled_by")
            .prefetch_related(
                Prefetch(
                    "service__center_assignments",
                    queryset=CenterServiceAssignment.objects.filter(
                        center__redeemable_programs__program_services__pk=self.kwargs[
                            "pk"
                        ],
                        is_active=True,
                    ).select_related("center"),
                ),
                "created_by",
            )
        )
        return qs



class ExternalCustomerAssociateListView(BaseListAPIView):
    """List associates linked to a external customer profile."""

    serializer_class = ExternalCustomerAssociateSerializer

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)
        qs = (
            CustomerAssociateAssignment.objects.annotate(
                full_name=Concat(
                    F("associate__user__first_name"),
                    Value(" "),
                    F("associate__user__last_name"),
                ),
            )
            .filter(
                search,
                customer_profile__customer__user__phone=phone_cleaned,
                **filter_kwargs
            )
            .annotate(
                role=FilteredRelation(
                    "associate__center_assignments__role",
                    condition=Q(
                        associate__center_assignments__center_id=F("center_id")
                    ),
                )
            )
            .select_related(
                "associate__user",
                "role",
            )
            .prefetch_related("center", "created_by")
            .order_by("-created_at")
        )
        return qs
