from django.db.models import Exists, OuterRef, Q, FilteredRelation, F, Subquery, Value
from django.db.models.functions import Coalesce

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
)
from accounts.customers.serializers import (
    CustomerAccountSerializer,
    CustomerAssociateAssignmentSerializer,
    CustomerCenterAssignmentSerializer,
    CustomerProfileSerializer,
    CenterCustomerProfileDetailSerializer,
    CustomerAssociateSerializer,
    BaseCustomerAssignedCenterSerializer,
)
from accounts.organizations.utils.db import (
    decrement_organization_clients_count,
)
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser, IsCustomerUser
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListAPIView,
    BaseRetrieveUpdateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseCreateAPIView,
)


class CustomerAccountProfileView(BaseRetrieveUpdateAPIView):
    """Views for customers to update their profiles"""

    permission_classes = [IsCustomerUser]
    serializer_class = CustomerAccountSerializer

    def get_object(self):
        qs = Customer.objects.select_related("user")
        return get_object_or_404(
            qs, detail="Invalid Customer profile", pk=self.kwargs.get("pk")
        )


class CustomerProfilesListView(BaseListAPIView):
    """View for customers to List all profiles"""

    permission_classes = [IsCustomerUser]
    serializer_class = CustomerProfileSerializer

    def get_customer(self):
        qs = Customer.objects.select_related("user")
        return get_object_or_404(
            qs, detail="Invalid Customer profile", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        filter_kwargs = {}
        is_active_query = self.request.query_params.get("is_active", None)

        if is_active_query is not None:
            filter_kwargs["is_active"] = bool(int(is_active_query))

        return CustomerProfile.objects.select_related("customer__user").filter(
            customer=self.get_customer(), **filter_kwargs
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
        decrement_customer_count(instance.center.pk)
        decrement_organization_clients_count()
        super().perform_destroy(instance)


class CustomerAvailableAssociateView(BaseListAPIView):
    """List associates at the center for this customer profile."""

    serializer_class = BaseCenterAssociateSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        subquery_filter_kwargs = {}
        user = self.request.user
        center_id = self.request.query_params.get("center_id", None)
        role_id = self.request.query_params.get("role_id", None)
        search_params = self.request.query_params.get("search", "").strip()

        if search_params:
            search |= Q(associate__user__first_name__istartswith=search_params)
            search |= Q(associate__user__first_name__icontains=search_params)
            search |= Q(associate__user__email__istartswith=search_params)
            search |= Q(associate__user__email__icontains=search_params)

        if center_id:
            filter_kwargs["center_id"] = center_id
            subquery_filter_kwargs["center_id"] = center_id
        if role_id:
            filter_kwargs["role_id"] = role_id
        account = get_user_account_type(user)

        if account == UserType.ASSOCIATE:
            associate = getattr(user, "associate", None)
            # filter_kwargs["associate__center_assignments__center_id"] = center_id
            # TODO: Implement the associate filtering here or remove this

        exists_subquery = CustomerAssociateAssignment.objects.filter(
            associate=OuterRef("pk"),
            **subquery_filter_kwargs,
        )

        return (
            AssociateCenterAssignment.objects.select_related("associate__user")
            .prefetch_related("created_by", "center")
            .annotate(
                exists=Exists(exists_subquery),
            )
            .filter(search, **filter_kwargs, is_admin=False)
            .order_by("-created_at")
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
        center_ids = self.request.query_params.getlist("center_id", [])

        search_param = self.request.query_params.get("search", "").strip()
        if search_param:
            search |= Q(associate__user__first_name__istartswith=search_param)
            search |= Q(associate__user__first_name__icontains=search_param)
            search |= Q(associate__user__user__email__istartswith=search_param)
            search |= Q(associate__user__user__email__icontains=search_param)

        account_type = get_user_account_type(user)
        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = associate

        if center_ids:
            filter_kwargs["center__in"] = center_ids

        qs = (
            CustomerAssociateAssignment.objects.filter(
                search, customer_profile_id=self.kwargs["pk"], **filter_kwargs
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
    serializer_class = BaseCustomerAssignedCenterSerializer
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
        )
        return qs
