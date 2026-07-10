from django.db import transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Concat

from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import get_object_or_404
from core.utils.views import (
    BaseCreateAPIView,
    BaseGenericAPIView,
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
)
from leads.models import Lead
from leads.serializers import (
    LeadConvertClientSerializer,
    LeadDetailSerializer,
    LeadListCreateSerializer,
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
        client_query = self.request.query_params.get("client", None)
        converted_query = self.request.query_params.get("converted", None)
        joined_query = self.request.query_params.get("joined", None)
        invited_query = self.request.query_params.get("invited", None)
        profile_query = self.request.query_params.get("profile", None)

        if client_query in ["0", "1"]:
            filter_kwargs["is_client"] = bool(int(client_query))
        if converted_query in ["0", "1"]:
            filter_kwargs["is_client"] = bool(int(converted_query))
        if invited_query in ["0", "1"]:
            filter_kwargs["is_invited"] = bool(int(invited_query))
        if joined_query in ["0", "1"]:
            filter_kwargs["is_joined"] = bool(int(joined_query))

        if profile_query in ["0", "1"]:
            _status = bool(int(profile_query))
            filter_kwargs['customer_profile__isnull'] = not _status

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
            if instance.is_joined:
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


class LeadConvertClientView(LeadActionMixin, BaseCreateAPIView):
    serializer_class = LeadConvertClientSerializer

    def perform_create(self, serializer: LeadConvertClientSerializer) -> None:
        serializer.save(
            lead=self.get_lead(),
            updated_by=self.request.user,
        )
