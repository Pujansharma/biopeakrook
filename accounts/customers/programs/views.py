from django.db.models import (
    BooleanField,
    ExpressionWrapper,
    F,
    Prefetch,
    Q,
    QuerySet,
)
from django.utils import timezone

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.customers.programs.serializers import (
    CustomerCompositeProgramSerializer,
    CustomerCompositeProgramServiceFilterSerializer,
    CustomerCompositeProgramServiceListSerializer,
    CustomerTherapyProgramSerializer,
)
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseGenericAPIView,
    BaseListAPIView,
    BaseListCreateAPIView,
)
from programs.composites.views import CompositeProgramViewMeta
from programs.models import ProgramService, TherapyProgram
from programs.services.utils.constants import ServiceCategory
from programs.utils.constants import ProgramType


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


class CustomerCompositeProgramViewMeta(CompositeProgramViewMeta):
    def get_center(self):
        center_identifier = self.request.headers.get("X-Center-ID")
        centers = Center.objects.filter(is_active=True)
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            centers = centers.filter(
                associate_assignments__associate=self.request.user.associate,
                associate_assignments__is_active=True,
            )
        return get_object_or_404(
            centers.distinct(),
            "No valid center found with the given ID.",
            pk=center_identifier,
        )

    def get_customer_profile(self, center: Center):
        filter_kwargs = {
            "is_active": True,
            "center_assignments__center": center,
            "center_assignments__is_active": True,
        }
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            filter_kwargs.update(
                {
                    "associate_assignments__associate": self.request.user.associate,
                    "associate_assignments__center": center,
                    "associate_assignments__is_active": True,
                }
            )
        customer_profiles = CustomerProfile.objects.filter(
            **filter_kwargs
        ).distinct()
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
            serializer,
    ) -> None:
        serializer.save(
            customer_profile=self.get_customer_profile(),
            created_by=self.request.user,
        )


class CustomerCompositeProgramsView(
    BaseListCreateAPIView,
    CustomerCompositeProgramViewMeta,
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CustomerCompositeProgramSerializer

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        search_params = self.request.query_params.get('search', "").strip()
        active_query = self.request.query_params.get("active")
        expired_query = self.request.query_params.get("expired")
        service_category_query = self.request.query_params.get('category')

        if search_params:
            search |= Q(composite_template__code__icontains=search_params)
            search |= Q(composite_template__name__icontains=search_params)
            search |= Q(composite_template__name__istartswith=search_params)
            search |= Q(program__uid__istartswith=search_params)
            search |= Q(program__uid__iexact=search_params)

        if active_query in {"0", "1"}:
            filter_kwargs["program__is_active"] = bool(int(active_query))

        if service_category_query:
            # program__program_services__service__service_category
            # pass
            filter_kwargs[
                'program__program_services__service__service_category'
            ] = service_category_query

        expired_filters = {
            "1": {"program__expires_at__lt": timezone.localdate()},
            "0": {"program__expires_at__gte": timezone.localdate()},
        }
        if expired_query and expired_query in expired_filters:
            filter_kwargs.update(expired_filters[expired_query])

        center = self.get_center()
        customer_profile = self.get_customer_profile(center)
        return self.get_composite_program_queryset(center.pk).filter(
            search, program__customer_profile=customer_profile,
            **filter_kwargs,
        ).distinct()

    def perform_create(
            self,
            serializer,
    ):
        center = self.get_center()
        serializer.save(
            customer_profile=self.get_customer_profile(center),
            center=center,
            created_by=self.request.user,
        )


class CustomerCompositeProgramServicesView(
    BaseListAPIView,
    CustomerCompositeProgramViewMeta,
):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CustomerCompositeProgramServiceListSerializer

    def get_filters(self):
        serializer = CustomerCompositeProgramServiceFilterSerializer(
            data=self.request.query_params
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def get_queryset(self):
        center = self.get_center()
        customer_profile = self.get_customer_profile(center)
        filters = self.get_filters()
        filter_kwargs = {
            "program__program_type": ProgramType.COMPOSITE,
            "program__customer_profile": customer_profile,
            "service__service_category__in": [
                ServiceCategory.ASSESSMENT,
                ServiceCategory.THERAPY,
            ],
        }

        service_category = filters.get("service_category")
        assignment_type = filters.get("assignment_type")
        composite_program_identifier = filters.get("composite_program")
        search = filters.get("search", "").strip()
        active = filters.get("active")

        if service_category:
            filter_kwargs["service__service_category"] = service_category
        if assignment_type:
            filter_kwargs["assignment_type"] = assignment_type
        if composite_program_identifier:
            filter_kwargs[
                "program__composite_program__pk"
            ] = composite_program_identifier
        if search:
            filter_kwargs["service__name__icontains"] = search
        if active is not None:
            filter_kwargs["is_active"] = bool(int(active))

        return (
            self.get_composite_program_service_queryset(center.pk)
            .select_related(
                "program",
                "program__composite_program",
                "program__composite_program__composite_template",
            )
            .filter(
                Q(program__center=center)
                | Q(program__redeemable_centers=center),
                **filter_kwargs,
            )
            .order_by("-created_at")
            .distinct()
        )
