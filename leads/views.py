from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Concat

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views import (
    BaseCreateAPIView,
    BaseListAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView, BaseGenericAPIView,
)
from leads.models import Lead
from leads.serializers import (
    LeadAssignCompositeSerializer,
    LeadAvailableCompositeSerializer,
    LeadCompositeAssignmentSerializer,
    LeadConvertClientSerializer,
    LeadDetailSerializer,
    LeadListCreateSerializer,
    LeadShareOnboardingSerializer,
)
from leads.utils.db import (
    decrement_leads_assigned,
    decrement_leads_converted,
    decrement_leads_inactive,
    decrement_leads_total,
)


class LeadsView(BaseListCreateAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = LeadListCreateSerializer

    def get_queryset(self) -> object:
        filter_kwargs = {}
        search = Q()
        search_query = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active", None)
        client_query = self.request.query_params.get("is_client", None)
        center_query = self.request.query_params.get("center_id", None)

        if active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))
        if client_query in ["0", "1"]:
            filter_kwargs["is_client"] = bool(int(client_query))
        if center_query:
            filter_kwargs["home_center__pk"] = center_query

        if search_query:
            search |= Q(first_name__istartswith=search_query)
            search |= Q(first_name__icontains=search_query)
            search |= Q(last_name__istartswith=search_query)
            search |= Q(last_name__icontains=search_query)
            search |= Q(full_name__istartswith=search_query)
            search |= Q(full_name__icontains=search_query)
            search |= Q(phone__istartswith=search_query)
            search |= Q(email__istartswith=search_query)
            search |= Q(email__icontains=search_query)

        return (
            Lead.objects.annotate(
                full_name=Concat(F("first_name"), Value(" "), F("last_name"))
            )
            .prefetch_related(
                "home_center",
                "created_by",
                "updated_by",
            )
            .select_related(
                "customer_profile",
                "customer_profile__customer",
                "customer_profile__customer__user",
            )
            .filter(search, **filter_kwargs)
        )

    def perform_create(self, serializer: LeadListCreateSerializer) -> None:
        serializer.save(created_by=self.request.user)


class LeadDetailView(BaseRetrieveUpdateDestroyAPIView):
    serializer_class = LeadDetailSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self) -> object:
        return Lead.objects.select_related(
            "home_center",
            "customer_profile",
            "customer_profile__customer",
            "customer_profile__customer__user",
            "created_by",
            "updated_by",
        )

    def perform_update(self, serializer: LeadDetailSerializer) -> None:
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance: Lead) -> None:
        with transaction.atomic():
            decrement_leads_total()
            if not instance.is_active:
                decrement_leads_inactive()
            if instance.is_client:
                decrement_leads_assigned()
            if instance.customer_profile or instance.converted_on:
                decrement_leads_converted()
            instance.delete()


class LeadActionMixin(BaseGenericAPIView):
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_lead(self) -> Lead:
        queryset = Lead.objects.select_related(
            "home_center",
            "customer_profile",
            "customer_profile__customer",
            "customer_profile__customer__user",
        )
        return get_object_or_404(
            queryset,
            "Lead not found with this ID",
            pk=self.kwargs["pk"],
        )


class LeadShareOnboardingView(LeadActionMixin, BaseCreateAPIView):
    serializer_class = LeadShareOnboardingSerializer

    def perform_create(self, serializer: LeadShareOnboardingSerializer) -> None:
        serializer.save(
            lead=self.get_lead(),
            created_by=self.request.user,
        )


class LeadConvertClientView(LeadActionMixin, BaseCreateAPIView):
    serializer_class = LeadConvertClientSerializer

    def perform_create(self, serializer: LeadConvertClientSerializer) -> None:
        serializer.save(
            lead=self.get_lead(),
            updated_by=self.request.user,
        )


class LeadAvailablePackagesView(LeadActionMixin, BaseListAPIView):
    serializer_class = LeadAvailableCompositeSerializer

    def get_queryset(self) -> list:
        lead = self.get_lead()

        return []


class LeadAssignPackageView(LeadActionMixin, BaseCreateAPIView):
    serializer_class = LeadAssignCompositeSerializer

    def perform_create(self, serializer: LeadAssignCompositeSerializer) -> None:
        lead = self.get_lead()
        serializer.save(lead=lead, created_by=self.request.user)


class LeadPackagesView(LeadActionMixin, BaseListAPIView):
    serializer_class = LeadCompositeAssignmentSerializer

    def get_queryset(self) -> list:
        lead = self.get_lead()
        return []
