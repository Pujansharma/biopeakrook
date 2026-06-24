from django.db.models import (
    BooleanField,
    Count,
    ExpressionWrapper,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    FilteredRelation,
    Value,
)
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone

from accounts.customers.models import (
    Customer,
    CustomerProfile,
    CustomerAssociateAssignment,
)
from accounts.notifications.models import UserNotification
from core.utils.exceptions import get_object_or_404
from core.utils.formatters import PhoneNumberFormat
from core.utils.helper import get_request_ip_address, get_request_user_agent
from core.utils.views.main import BaseListAPIView, BaseRetrieveAPIView, BaseCreateAPIView
from external.serializers import (
    CustomerProfileSummarySerializer,
    ExternalProgramServiceSerializer,
    CustomerTherapyProgramSerializer,
    CustomerTherapyProgramDetailSerializer,
    CustomerServiceDetailSerializer,
    ExternalCustomerAssociateSerializer, CustomerFirebaseTokenSerializer, ExternalCustomerNotificationSerializer,
    CustomerFirebaseTokenDeregisterSerializer,
)
from programs.models import (
    Program,
    RedemptionHistory,
    TherapyProgram,
    TherapyProgramService,
)
from programs.serializers import ProgramServiceRedemptionHistorySerializer
from programs.services.models import CenterServiceAssignment


class ExternalUserProgramView(BaseListAPIView):
    serializer_class = CustomerTherapyProgramSerializer

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
            TherapyProgram.objects.annotate(
                is_complete=ExpressionWrapper(
                    Q(sessions_count=F("sessions_used") + F("sessions_cancelled")),
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
                    programs_base.annotate(
                        total=Sum("therapy_program__sessions_count")
                    ).values("total")[:1]
                ),
                0,
            ),
            sessions_used=Coalesce(
                Subquery(
                    programs_base.annotate(
                        total=Sum("therapy_program__sessions_used")
                    ).values("total")[:1]
                ),
                0,
            ),
            sessions_cancelled=Coalesce(
                Subquery(
                    programs_base.annotate(
                        total=Sum("therapy_program__sessions_cancelled")
                    ).values("total")[:1]
                ),
                0,
            ),
            sessions_expired=Coalesce(
                Subquery(
                    programs_base.filter(expires_at__lt=timezone.localdate())
                    .annotate(
                        total=Sum(
                            F("therapy_program__sessions_count")
                            - F("therapy_program__sessions_used")
                        )
                    )
                    .values("total")[:1]
                ),
                0,
            ),
            programs_complete=Coalesce(
                Subquery(
                    programs_base.filter(
                        is_active=True,
                        therapy_program__sessions_count=(
                                F("therapy_program__sessions_used")
                                + F("therapy_program__sessions_cancelled")
                        ),
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
    serializer_class = CustomerTherapyProgramDetailSerializer

    def get_queryset(self):
        phone_query = self.request.query_params.get("phone", None)

        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)

        return (
            TherapyProgram.objects.filter(
                program__customer_profile__customer__user__phone=phone_cleaned,
            )
            .select_related(
                "program",
            )
            .prefetch_related()
        )


class ExternalUserProgramServicesListView(BaseListAPIView):
    serializer_class = ExternalProgramServiceSerializer

    def get_queryset(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)
        qs = (
            TherapyProgramService.objects.filter(
                program_service__program__therapy_program__pk=self.kwargs["pk"],
                program_service__program__customer_profile__customer__user__phone=phone_cleaned,
            )
            .select_related(
                "program_service",
                "program_service__cancelled_by",
                "program_service__created_by",
                "program_service__service",
            )
            .prefetch_related(
                Prefetch(
                    "program_service__service__center_assignments",
                    queryset=CenterServiceAssignment.objects.filter(
                        center__redeemable_programs__therapy_program__pk=self.kwargs[
                            "pk"
                        ],
                        is_active=True,
                    ).select_related("center"),
                ),
            )
        )
        return qs


class ExternalUserProgramServiceRedemptionHistory(BaseListAPIView):
    serializer_class = ProgramServiceRedemptionHistorySerializer

    def get_therapy_program_service(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_cleaned = PhoneNumberFormat(phone_query).clean(raise_exception=False)
        queryset = TherapyProgramService.objects.filter(
            program_service__program__customer_profile__customer__user__phone=phone_cleaned,
        ).select_related("program_service__program__customer_profile__customer__user")
        return get_object_or_404(
            queryset, "Therapy program service not found", pk=self.kwargs["pk"]
        )

    def get_queryset(self):
        therapy_program_service = self.get_therapy_program_service()
        return RedemptionHistory.objects.filter(
            therapy_program_service=therapy_program_service
        ).select_related("redeemed_by", "redeem_center")


class ExternalUserProgramServiceDetailView(BaseRetrieveAPIView):
    serializer_class = CustomerServiceDetailSerializer

    def get_queryset(self):
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)
        queryset = (
            TherapyProgramService.objects.filter(
                program_service__program__customer_profile__customer__user__phone=phone_cleaned,
            )
            .select_related(
                "program_service",
                "program_service__cancelled_by",
                "program_service__created_by",
                "program_service__program",
                "program_service__program__therapy_program",
                "program_service__service",
            )
            .prefetch_related(
                Prefetch(
                    "program_service__service__center_assignments",
                    queryset=CenterServiceAssignment.objects.filter(
                        center__redeemable_programs__program_services__therapy_service__pk=self.kwargs[
                            "pk"
                        ],
                        is_active=True,
                    ).select_related("center"),
                ),
            )
        )
        return queryset


class ExternalCustomerAssociateListView(BaseListAPIView):
    """List associates linked to an external customer profile."""

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
                associate__is_active=True,
                **filter_kwargs,
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


class CustomerFirebaseTokenView(BaseCreateAPIView):
    serializer_class = CustomerFirebaseTokenSerializer

    def perform_create(self, serializer):
        ip_address = get_request_ip_address(self.request)
        user_agent = get_request_user_agent(self.request)
        serializer.save(
            ip_address=ip_address,
            user_agent=user_agent,
        )


class CustomerFirebaseTokenDeregisterView(BaseCreateAPIView):
    serializer_class = CustomerFirebaseTokenDeregisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("Firebase token deregistered successfully")
    

class CustomerNotificationsView(BaseListAPIView):
    serializer_class = ExternalCustomerNotificationSerializer

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)

        is_read_query = self.request.query_params.get('read', None)
        if is_read_query and is_read_query in ['0', '1']:
            filter_kwargs['seen_at__isnull'] = not bool(int(is_read_query))

        qs = UserNotification.objects.filter(
            search, user__phone=phone_cleaned, **filter_kwargs
        )
        return qs


class CustomerNotificationDetailView(BaseRetrieveAPIView):
    serializer_class = ExternalCustomerNotificationSerializer

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        phone_query = self.request.query_params.get("phone", None)
        phone_formatter = PhoneNumberFormat(phone_query)
        phone_cleaned = phone_formatter.clean(raise_exception=False)

        qs = UserNotification.objects.filter(
            search, user__phone=phone_cleaned, **filter_kwargs
        )
        return qs

    def get_object(self):
        qs = self.get_queryset()
        instance = get_object_or_404(qs, "Notification not found", pk=self.kwargs['pk'])
        if not instance.seen_at:
            instance.seen_at = timezone.localtime()
            instance.save(update_fields=['seen_at'])
        return instance
