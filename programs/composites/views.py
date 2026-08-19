from django.db.models import (
    BooleanField,
    Case,
    Exists,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Value,
    When,
)

from accounts.centers.models import Center
from accounts.customers.models import CustomerCenterAssignment
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import (
    BaseAssociateRBACPermission,
    IsAdminUser,
    IsAssociateUser,
    PackagesPermission,
)
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseCreateAPIView,
    BaseGenericAPIView,
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateAPIView,
    BaseUpdateAPIView,
)
from programs.composites.models import (
    CompositeServicePrerequisite,
    CompositeTemplate,
    CompositeTemplateService,
)
from programs.composites.serializers import (
    CompositeAddOnSerializer,
    CompositeAvailablePrerequisiteServiceSerializer,
    CompositePrerequisiteServiceSerializer,
    CompositeProgramCancelSerializer,
    CompositeProgramDetailSerializer,
    CompositeProgramServiceSerializer,
    CompositeServicePrerequisiteSerializer,
    CompositeTemplateSerializer,
    CompositeTemplateServiceSerializer,
)
from programs.models import CompositeProgram, Program, ProgramService
from programs.services.models import (
    CenterServiceAssignment,
    ServiceProductAssignment,
)


class CompositeTemplateServiceViewMeta(BaseGenericAPIView):
    def get_queryset(self):
        locked_service = ProgramService.objects.filter(service=OuterRef("service"))
        center_assignments = CenterServiceAssignment.objects.filter(
            is_active=True,
            center__is_active=True,
        ).select_related("center")
        product_assignments = ServiceProductAssignment.objects.filter(
            is_active=True,
        ).select_related("product")
        related_services = CompositeTemplateService.objects.select_related(
            "service"
        ).order_by("created_at")
        qs = (
            CompositeTemplateService.objects.select_related(
                "service",
                "service__created_by",
                "prerequisite",
            )
            .annotate(is_locked=Exists(locked_service))
            .prefetch_related(
                Prefetch(
                    "service__center_assignments",
                    queryset=center_assignments,
                ),
                Prefetch(
                    "service__product_assignments",
                    queryset=product_assignments,
                ),
                Prefetch(
                    "prerequisite__related_services",
                    queryset=related_services[:3],
                    to_attr="related_service_preview",
                ),
            )
        )
        return qs


class CompositeTemplateViewMeta(CompositeTemplateServiceViewMeta):
    def get_queryset(self):
        composite_template_services = super().get_queryset()
        qs = CompositeTemplate.objects.select_related(
            "created_by"
        ).prefetch_related(
            Prefetch(
                "services",
                queryset=composite_template_services[:3],
                to_attr="service_preview",
            )
        )
        return qs


class CompositeServicePrerequisiteViewMeta(BaseGenericAPIView):

    def get_template_service(self) -> CompositeTemplateService:
        qs = CompositeTemplateService.objects.select_related(
            "composite_template",
            "service",
        )
        return get_object_or_404(
            qs,
            "Composite template service not found",
            pk=self.kwargs["pk"],
        )

    def get_object(self) -> CompositeServicePrerequisite:
        template_service = self.get_template_service()
        prerequisite, _ = (
            CompositeServicePrerequisite.objects.select_related(
                "template_service",
                "template_service__composite_template",
                "template_service__service",
                "created_by",
            )
            .prefetch_related(
                Prefetch(
                    "related_services",
                    queryset=CompositeTemplateService.objects.select_related(
                        "service"
                    )[:3],
                    to_attr="related_service_preview",
                )
            )
            .get_or_create(
                template_service=template_service,
            )
        )
        self.check_object_permissions(self.request, prerequisite)
        return prerequisite


class CompositeProgramViewMeta(BaseGenericAPIView):
    def get_composite_program_queryset(self, center_identifier=None):
        primary_center_assignments = CustomerCenterAssignment.objects.filter(
            is_primary=True
        ).select_related("center")
        return CompositeProgram.objects.select_related(
            "program",
            "program__center",
            "program__created_by",
            "program__cancelled_by",
            "program__customer_profile__customer__user",
            "composite_template",
        ).prefetch_related(
            "program__redeemable_centers",
            Prefetch(
                "program__program_services",
                queryset=self.get_composite_program_service_queryset(
                    center_identifier
                )[:3],
                to_attr="service_preview",
            ),
            Prefetch(
                "program__customer_profile__center_assignments",
                queryset=primary_center_assignments,
                to_attr="primary_center_assignments",
            ),
        )

    def get_composite_program_service_queryset(self, center_identifier=None):
        filter_kwargs = {
            "service": OuterRef("service"),
            "is_active": True,
            "center__is_active": True,
        }
        if center_identifier:
            filter_kwargs["center__pk"] = center_identifier
        elif get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            filter_kwargs["center__associate_assignments__associate"] = (
                self.request.user.associate
            )
            filter_kwargs["center__associate_assignments__is_active"] = True
        else:
            filter_kwargs["center__pk"] = None

        program_services = ProgramService.objects.select_related(
            "service",
            "created_by",
            "cancelled_by",
            "therapy_service",
            "assessment_service",
            "consultation_service",
        )
        center_service_assignment = CenterServiceAssignment.objects.filter(
            **filter_kwargs
        )
        return program_services.annotate(
            can_redeem=Case(
                When(service__is_global=True, then=Value(True)),
                default=Exists(center_service_assignment),
                output_field=BooleanField(),
            )
        )

    def get_associate_program_queryset(self, center_identifier=None):
        filter_kwargs = {
            "is_active": True,
            "associate_assignments__associate": self.request.user.associate,
            "associate_assignments__is_active": True,
        }
        if center_identifier:
            filter_kwargs["pk"] = center_identifier
        centers = Center.objects.filter(**filter_kwargs)
        return Program.objects.filter(
            Q(center__in=centers) | Q(redeemable_centers__in=centers)
        ).distinct()


class CompositeTemplatesView(BaseListCreateAPIView, CompositeTemplateViewMeta):
    serializer_class = CompositeTemplateSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_params = self.request.query_params.get('search', '').strip()
        code_params = self.request.query_params.get('code', '').strip()
        if search_params:
            search |= Q(code__icontains=search_params)
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)

        active_query = self.request.query_params.get('active', None)
        if active_query and active_query in ['0', '1']:
            filter_kwargs['is_active'] = bool(int(active_query))

        if code_params:
            filter_kwargs = {'code__icontains': code_params}

        qs = super().get_queryset().filter(search, **filter_kwargs)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CompositeTemplateDetailView(
    BaseRetrieveUpdateAPIView, CompositeTemplateViewMeta
):
    serializer_class = CompositeTemplateSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]


class CompositeTemplateServicesListView(
    BaseListAPIView,
    CompositeTemplateServiceViewMeta,
):
    serializer_class = CompositeTemplateServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_composite_template(self) -> CompositeTemplate:
        qs = CompositeTemplate.objects.filter()
        return get_object_or_404(
            qs,
            "Composite template not found with this ID.",
            pk=self.kwargs["pk"],
        )

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        category = self.request.query_params.get('category', None)
        search_params = self.request.query_params.get('search', "").strip()
        if category:
            filter_kwargs['service__service_category'] = category
        if search_params:
            search |= Q(service__name__istartswith=search_params)
            search |= Q(service__name__icontains=search_params)
        qs = super().get_queryset().filter(
            search,
            composite_template=self.get_composite_template(),
            **filter_kwargs
        )
        return qs


class CompositeServicePrerequisiteDetailView(
    BaseUpdateAPIView,
    CompositeServicePrerequisiteViewMeta,
):
    serializer_class = CompositeServicePrerequisiteSerializer
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]


class CompositePrerequisiteServicesListView(
    BaseListAPIView,
    CompositeServicePrerequisiteViewMeta,
):
    serializer_class = CompositePrerequisiteServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self) -> QuerySet[CompositeTemplateService]:
        prerequisite = self.get_object()
        return CompositeTemplateService.objects.select_related(
            "service"
        ).filter(
            related_prerequisites=prerequisite,
        ).order_by("-created_at")


class CompositeAvailablePrerequisiteServicesListView(
    BaseListAPIView,
    CompositeServicePrerequisiteViewMeta,
):
    serializer_class = CompositeAvailablePrerequisiteServiceSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self) -> QuerySet[CompositeTemplateService]:
        filter_kwargs = {}
        prerequisite = self.get_object()
        service_category_query = self.request.query_params.get('category')
        if service_category_query:
            filter_kwargs['service__service_category'] = service_category_query
        existing_related_services = CompositeTemplateService.objects.filter(
            pk=OuterRef("pk"),
            related_prerequisites=prerequisite,
        )
        return (
            CompositeTemplateService.objects.select_related("service")
            .filter(
                composite_template=prerequisite.template_service.composite_template,
                **filter_kwargs,
            )
            .exclude(pk=self.kwargs['pk'])
            .annotate(is_exists=Exists(existing_related_services))
            .order_by("-is_exists", "-created_at")
        )


class CompositeProgramDetailView(
    BaseRetrieveUpdateAPIView,
    CompositeProgramViewMeta,
):
    serializer_class = CompositeProgramDetailSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        center_identifier = getattr(self.request, 'center_id', None)
        account_type = get_user_account_type(self.request.user)
        composite_programs = self.get_composite_program_queryset(center_identifier)
        qs = composite_programs.filter(**filter_kwargs)
        if account_type == UserType.ASSOCIATE:
            filter_kwargs["program__in"] = self.get_associate_program_queryset(
                center_identifier
            )
        return qs


class CompositeProgramServicesListView(
    BaseListAPIView,
    CompositeProgramViewMeta,
):
    serializer_class = CompositeProgramServiceSerializer
    permission_classes = [IsAdminUser | BaseAssociateRBACPermission]

    def get_queryset(self):
        filter_kwargs = {
            "program__composite_program__pk": self.kwargs["pk"],
        }
        service_category = self.request.query_params.get('category')
        if service_category:
            filter_kwargs['service__service_category'] = service_category
        assignment_type = self.request.query_params.get("assignment_type")
        if assignment_type:
            filter_kwargs["assignment_type"] = assignment_type
        center_identifier = getattr(self.request, 'center_id', None)
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            filter_kwargs["program__in"] = self.get_associate_program_queryset(
                center_identifier
            )
        qs = self.get_composite_program_service_queryset(
            center_identifier
        ).filter(**filter_kwargs)
        return qs


class CompositeProgramCancelView(BaseCreateAPIView, CompositeProgramViewMeta):
    serializer_class = CompositeProgramCancelSerializer
    permission_classes = [IsAdminUser | PackagesPermission]

    def get_composite_program(self):
        center = self.get_center()
        composite_programs = self.get_composite_program_queryset(center.pk).filter(
            Q(program__center=center) | Q(program__redeemable_centers=center)
        ).distinct()
        return get_object_or_404(
            composite_programs,
            "Composite program not found with this ID.",
            pk=self.kwargs["pk"],
        )

    def get_center(self):
        center_identifier = getattr(self.request, 'center_id', None)
        if not center_identifier:
            self.raise_bad_request("X-Center-ID header is required.")
        centers = Center.objects.filter()
        return get_object_or_404(
            centers,
            "Center not found with this ID.",
            pk=center_identifier,
        )

    def perform_create(
            self,
            serializer,
    ):
        composite_program = self.get_composite_program()
        serializer.save(
            composite_program=composite_program,
            center=self.get_center(),
            cancelled_by=self.request.user,
        )


class CompositeAddOnView(BaseCreateAPIView, CompositeProgramViewMeta):
    serializer_class = CompositeAddOnSerializer
    permission_classes = [IsAdminUser | BaseAssociateRBACPermission]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        center_identifier = getattr(self.request, "center_id", None)
        composite_programs = self.get_composite_program_queryset(center_identifier)
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            composite_programs = composite_programs.filter(
                program__in=self.get_associate_program_queryset(center_identifier)
            )
        context["composite_program_queryset"] = composite_programs.distinct()
        return context

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
