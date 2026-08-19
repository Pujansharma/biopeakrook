from django.db.models import Exists, OuterRef, Q, FilteredRelation, F, Subquery, Value
from django.db.models.functions import Coalesce, Concat
from django.db.models.query import Prefetch
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.associates.models import AssociateCenterAssignment
from accounts.associates.serializers import BaseCenterAssociateSerializer
from accounts.centers.models import Center
from accounts.centers.serializers import CustomerAvailableCenterSerializer
from accounts.centers.utils.db import decrement_customer_count
from accounts.customers.models import (
    Customer,
    CustomerAssociateAssignment,
    CustomerCenterAssignment,
    CustomerProfile,
    CustomerProfileAddress, CustomerProfileFeature,
)
from accounts.customers.programs.serializers import (
    CustomerServiceDocumentSerializer,
)
from accounts.customers.serializers import (
    CustomerAccountSerializer,
    CustomerAssociateAssignmentSerializer,
    CustomerCenterAssignmentSerializer,
    CustomerProfileSerializer,
    CenterCustomerProfileDetailSerializer,
    CustomerAssociateSerializer,
    CustomerProfileFeatureSerializer, MinimalCustomerAssignedCenterSerializer,
    CustomerProfileAddressSerializer,
    CustomerLeadProfileSerializer,
    build_customer_lead_profile_fallback,
    get_main_customer_profile_for_user,
)
from accounts.organizations.utils.db import (
    decrement_organization_clients_count,
)
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.exceptions import get_object_or_404
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseListAPIView,
    BaseRetrieveAPIView,
    BaseRetrieveUpdateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseCreateAPIView,
    BaseListCreateAPIView, BaseGenericAPIView,
)
from leads.models import Lead
from programs.services.models import ServiceDocument


class CustomerProfileMeta(BaseGenericAPIView):

    def get_customer_for_user(self):
        qs = Customer.objects.select_related("user")
        return get_object_or_404(
            qs, detail="Invalid Customer profile", pk=self.request.user.pk
        )

    def get_customer_profile(self):
        filter_kwargs = {}
        if get_user_account_type(self.request.user) == UserType.CUSTOMER:
            filter_kwargs["customer"] = self.request.user.customer
        customer_profiles = CustomerProfile.objects.filter(**filter_kwargs)
        return get_object_or_404(
            customer_profiles,
            "Customer profile with this ID not found.",
            pk=self.kwargs["pk"],
        )


class CustomerProfileDocumentsListView(BaseListAPIView, CustomerProfileMeta):
    serializer_class = CustomerServiceDocumentSerializer
    permission_classes = [IsAdminUser | IsAssociateUser | IsCustomerUser]

    def get_queryset(self):
        search = Q()
        customer_profile = self.get_customer_profile()
        filter_kwargs = {
            "result__program_service__program__customer_profile": customer_profile,
        }
        search_query = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active")
        document_type = self.request.query_params.get("document_type")
        document_category = self.request.query_params.get("document_category")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if search_query:
            search |= Q(filename__icontains=search_query)
            search |= Q(result__provider_name__icontains=search_query)
            search |= Q(result__product_name__icontains=search_query)
            search |= Q(
                result__program_service__service__name__icontains=search_query
            )
        if active_query in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query))
        if document_type:
            filter_kwargs["result__document_type"] = document_type
        if document_category:
            filter_kwargs["document_category"] = document_category
        if date_from:
            filter_kwargs["result__sample_collection_date__gte"] = date_from
        if date_to:
            filter_kwargs["result__sample_collection_date__lte"] = date_to
        if date_from and date_to and date_from > date_to:
            self.raise_bad_request("Date to must be on or after date from.")

        return (
            ServiceDocument.objects.select_related(
                "result",
                "result__product",
                "result__program_service",
                "result__program_service__program",
                "result__program_service__program__composite_program",
                "result__program_service__program__composite_program__composite_template",
                "result__program_service__service",
            )
            .filter(search, **filter_kwargs)
            .order_by("-created_at")
        )


class CustomerAccountProfileView(BaseRetrieveUpdateAPIView, CustomerProfileMeta):
    """Views for customers to update their profiles"""

    permission_classes = [IsCustomerUser]
    serializer_class = CustomerAccountSerializer

    def get_object(self):
        return self.get_customer_for_user()


class CustomerLeadProfileView(BaseRetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerLeadProfileSerializer

    def get_queryset(self):
        return Lead.objects.select_related(
            "customer_profile__customer__user",
            "home_center",
        ).filter(phone=self.request.user.phone)

    def get(self, request, *args, **kwargs):
        lead = self.get_queryset().first()
        if lead:
            serializer = self.get_serializer(lead)
            return Response({"success": True, "data": serializer.data})

        customer_profile = get_main_customer_profile_for_user(request.user)
        if customer_profile:
            data = build_customer_lead_profile_fallback(
                customer_profile,
                context=self.get_serializer_context(),
            )
            return Response({"success": True, "data": data})

        raise NotFound("Lead not found")


class CustomerProfilesListView(BaseListAPIView):
    """View for customers to List all profiles"""

    permission_classes = [IsCustomerUser]
    serializer_class = CustomerProfileSerializer

    def get_queryset(self):
        filter_kwargs = {}
        is_active_query = self.request.query_params.get("is_active", None)

        if is_active_query is not None:
            filter_kwargs["is_active"] = bool(int(is_active_query))

        return CustomerProfile.objects.select_related("customer__user").filter(
            customer=self.get_customer_for_user(), **filter_kwargs
        )


class CustomerProfileDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Retrieve/update/delete a customer profile. Accessible by admins and associates."""

    serializer_class = CenterCustomerProfileDetailSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}

        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            associate = getattr(self.request.user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = associate

        return CustomerCenterAssignment.objects.select_related(
            "customer_profile__customer__user",
        ).prefetch_related(
            Prefetch(
                "customer_profile__center_assignments",
                queryset=CustomerCenterAssignment.objects.filter(
                    is_primary=True
                ).select_related("center"),
                to_attr="primary_center_assignments",
            ),
        ).filter(**filter_kwargs)

    def get_object(self):
        qs = self.get_queryset()
        header_center_id = self.request.headers.get("x-center-id", None)
        query_center_id = self.request.query_params.get("center_id", None)
        center_id = header_center_id or query_center_id or None
        return get_object_or_404(
            qs,
            center_id=center_id,
            customer_profile__id=self.kwargs["pk"],
        )

    def perform_destroy(self, instance: CustomerCenterAssignment):
        if instance.customer_profile.is_converted:
            decrement_customer_count(instance.center.pk)
            decrement_organization_clients_count()
        super().perform_destroy(instance)


class CustomerAvailableAssociateView(BaseListAPIView):
    """List associates at the center for this customer profile."""

    serializer_class = BaseCenterAssociateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_customer_profile(self):
        filter_kwargs = {}
        center_id = self.request.query_params.get("center_id", None)
        if center_id:
            filter_kwargs["center_assignments__center_id"] = center_id
        qs = CustomerProfile.objects.filter(**filter_kwargs)
        return get_object_or_404(
            qs, "Customer profile not found in this center", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        subquery_filter_kwargs = {}
        user = self.request.user
        customer_profile = self.get_customer_profile()
        center_id = self.request.query_params.get("center_id", None)
        role_id = self.request.query_params.get("role_id", None)
        search_params = self.request.query_params.get("search", "").strip()

        if search_params:
            search |= Q(associate__user__email__istartswith=search_params)
            search |= Q(associate__user__email__icontains=search_params)
            search |= Q(full_name__istartswith=search_params)
            search |= Q(full_name__icontains=search_params)

        if center_id:
            filter_kwargs["center_id"] = center_id
            subquery_filter_kwargs["center_id"] = center_id
        if role_id:
            filter_kwargs["role_id"] = role_id
        account = get_user_account_type(user)

        if account == UserType.ASSOCIATE:
            associate = getattr(user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = associate

        exists_subquery = CustomerAssociateAssignment.objects.filter(
            associate=OuterRef("associate_id"),
            customer_profile=customer_profile,
            **subquery_filter_kwargs,
        )

        return (
            AssociateCenterAssignment.objects.select_related("associate__user")
            .prefetch_related("created_by", "center")
            .annotate(
                exists=Exists(exists_subquery),
                full_name=Concat(
                    F("associate__user__first_name"),
                    Value(" "),
                    F("associate__user__last_name"),
                ),
            )
            .filter(search, **filter_kwargs, is_admin=False)
            .order_by("-exists", "-created_at")
        )


class CustomerLinkAssociateView(BaseCreateAPIView):
    """Link an associate to a customer profile at a center."""

    permission_classes = [IsAdminUser]
    serializer_class = CustomerAssociateAssignmentSerializer

    def perform_create(self, serializer):
        serializer.save(
            customer_profile_id=self.kwargs["pk"],
            created_by=self.request.user,
        )


class CustomerAssociateListView(BaseListAPIView):
    """List associates linked to a customer profile at a center."""

    serializer_class = CustomerAssociateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        user = self.request.user
        center_ids = set(
            filter(None, self.request.query_params.getlist("center_id", []))
        )
        header_center_id = getattr(self.request, "center_id", None)
        role_id = self.request.query_params.get("role_id", None)

        if header_center_id:
            center_ids = {header_center_id}

        if role_id:
            filter_kwargs["current_center_assignment__role"] = role_id

        search_param = self.request.query_params.get("search", "").strip()
        if search_param:
            search |= Q(associate__user__email__istartswith=search_param)
            search |= Q(full_name__istartswith=search_param)

        account_type = get_user_account_type(user)
        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = associate

        if center_ids:
            filter_kwargs["center__in"] = center_ids

        qs = (
            CustomerAssociateAssignment.objects.annotate(
                full_name=Concat(
                    F("associate__user__first_name"),
                    Value(" "),
                    F("associate__user__last_name"),
                ),
                current_center_assignment=FilteredRelation(
                    "associate__center_assignments",
                    condition=Q(
                        associate__center_assignments__center=F("center")
                    ),
                ),
            )
            .filter(search, customer_profile_id=self.kwargs["pk"], **filter_kwargs)
            .select_related(
                "associate__user",
                "current_center_assignment__role",
            )
            .prefetch_related("center", "created_by")
            .order_by("-created_at")
            .distinct()
        )

        return qs


class CustomerAvailableCenterView(BaseListAPIView):
    """List all centers annotated with exists/is_primary for a customer profile."""

    serializer_class = CustomerAvailableCenterSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_customer_profile(self):
        qs = CustomerProfile.objects.select_related()
        return get_object_or_404(qs, pk=self.kwargs["pk"])

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        search_params = self.request.query_params.get("search", "").strip()
        active_param = self.request.query_params.get("active", None)
        if active_param and active_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_param))
        if search_params:
            search |= Q(name__istartswith=search_params)
            search |= Q(name__icontains=search_params)
            search |= Q(code__istartswith=search_params)

        customer_profile = self.get_customer_profile()
        exists_subquery = CustomerCenterAssignment.objects.filter(
            customer_profile=customer_profile, center=OuterRef("pk")
        )
        is_primary_subquery = CustomerCenterAssignment.objects.filter(
            customer_profile=customer_profile, center=OuterRef("pk")
        ).values("is_primary")

        return Center.objects.annotate(
            exists=Exists(exists_subquery),
            is_primary=Coalesce(Subquery(is_primary_subquery), Value(False)),
        ).filter(search, is_primary=False, **filter_kwargs)


class CustomerCenterLinkView(BaseCreateAPIView):
    """Link or unlink centers for a customer profile."""

    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CustomerCenterAssignmentSerializer

    def perform_create(self, serializer):
        serializer.save(
            customer_profile_id=self.kwargs["pk"],
            created_by=self.request.user,
        )


class CustomerCenterListView(BaseListAPIView):
    serializer_class = MinimalCustomerAssignedCenterSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        user = self.request.user

        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            search |= Q(center__name__istartswith=search_params)
            search |= Q(center__name__icontains=search_params)

        qs = (
            CustomerCenterAssignment.objects.select_related("center")
            .prefetch_related()
            .filter(search, customer_profile_id=self.kwargs["pk"])
            .order_by('-is_primary', '-created_at')
        )
        return qs


class CustomerProfileAddressView(BaseListCreateAPIView):
    serializer_class = CustomerProfileAddressSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_customer_profile(self):
        qs = CustomerProfile.objects.filter()
        return get_object_or_404(
            qs, "No customer profile found with the given ID", pk=self.kwargs["pk"]
        )

    def get_queryset(self):
        qs = (
            CustomerProfileAddress.objects.filter(
                customer_profile=self.get_customer_profile()
            )
            .select_related(
                "customer_profile",
                "customer_profile__customer",
            )
            .order_by("-is_default", "-created_at")
        )

        return qs

    def perform_create(self, serializer):
        serializer.save(
            customer_profile=self.get_customer_profile(),
        )


class CustomerProfileFeatureView(BaseRetrieveUpdateAPIView):
    serializer_class = CustomerProfileFeatureSerializer
    permission_classes = [IsAdminUser | IsAssociateUser | (IsCustomerUser & ReadOnly)]

    def get_customer_profile(self):
        filter_kwargs = {}
        user = self.request.user
        account_type = get_user_account_type(user)
        if account_type == UserType.CUSTOMER:
            customer = getattr(user, 'customer')
            filter_kwargs['customer'] = customer

        qs = CustomerProfile.objects.filter(
            **filter_kwargs
        )
        return get_object_or_404(qs, "Customer profile not found", pk=self.kwargs['pk'])

    def get_object(self):
        instance, _ = CustomerProfileFeature.objects.get_or_create(
            customer_profile=self.get_customer_profile()
        )
        return instance
