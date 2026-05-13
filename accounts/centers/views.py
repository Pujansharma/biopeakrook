from django.db.models import Prefetch, Q, ProtectedError, RestrictedError

from accounts.associates.models import AssociateCenterAssignment, AssociateRole
from accounts.associates.serializers import (
    CenterAssociateSerializer,
    AssociateRoleSerializer,
)
from accounts.centers.models import Center, CenterOperatingHour
from accounts.centers.serializers import (
    CenterSerializer,
    CenterDetailSerializer,
    CenterWorkingHourSerializer,
)
from accounts.customers.models import CustomerCenterAssignment
from accounts.customers.serializers import CenterCustomerProfileHomeCenterSerializer
from accounts.organizations.utils.db import decrement_organization_centers_count
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import (
    IsAdminUser,
    IsAssociateUser,
    IsCustomerUser,
)
from core.utils.exceptions import get_object_or_404
from core.utils.log import logger
from core.utils.permissions import ReadOnly
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseGenericAPIView,
)


class CentersView(BaseListCreateAPIView):
    permission_classes = [IsAdminUser | (IsAssociateUser & ReadOnly)]
    serializer_class = CenterSerializer

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        search_params = self.request.query_params.get("search", "").strip()
        active_query_param = self.request.query_params.get("active", None)
        if active_query_param and active_query_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query_param))
        if search_params:
            search |= Q(name__istartswith=search_params) | Q(
                code__icontains=search_params
            )
        if associate := getattr(self.request.user, "associate", None):
            filter_kwargs["associate_assignments__associate"] = associate

        return Center.objects.prefetch_related("created_by").filter(
            search, **filter_kwargs
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CenterViewMeta(BaseGenericAPIView):
    @classmethod
    def get_center_queryset(cls):
        return Center.objects.prefetch_related("created_by")

    def get_center(self):
        qs = self.get_center_queryset()
        pk = self.kwargs.get("pk")
        return get_object_or_404(qs, "The selected center could not be found", pk=pk)


class CenterDetailView(BaseRetrieveUpdateDestroyAPIView, CenterViewMeta):
    """Center ID from URL path parameter."""

    serializer_class = CenterDetailSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        user = self.request.user
        account_type = get_user_account_type(user)

        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate")
            filter_kwargs["associate_assignments__associate"] = associate

        return self.get_center_queryset().filter(**filter_kwargs)

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
            decrement_organization_centers_count()
        except ProtectedError, RestrictedError:
            logger.exception(msg="Error in Center DELETE", exc_info=True)
            self.raise_bad_request(
                "This center cannot be deleted since some objects are dependant on it"
            )


class CenterOperatingHoursView(BaseListCreateAPIView, CenterViewMeta):
    permission_classes = [
        IsAdminUser | (IsAssociateUser & ReadOnly) | (IsCustomerUser & ReadOnly)
    ]
    serializer_class = CenterWorkingHourSerializer

    def get_queryset(self):
        center = self.get_center()
        return CenterOperatingHour.objects.filter(center=center)

    def perform_create(self, serializer):
        center = self.get_center()
        serializer.save(center=center)


class CenterAssociateListView(BaseListCreateAPIView, CenterViewMeta):
    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = CenterAssociateSerializer

    def get_queryset(self):
        center = self.get_center()
        search = Q()
        filter_kwargs = {}
        search_params = self.request.query_params.get("search", "").strip()
        is_admin = self.request.query_params.get("admin", None)
        active_param = self.request.query_params.get("active", None)
        if active_param and active_param in ["0", "1"]:
            filter_kwargs["associate__user__is_active"] = bool(int(active_param))
        if search_params:
            search |= Q(associate__user__email__istartswith=search_params)
            search |= Q(associate__user__email__icontains=search_params)
            search |= Q(associate__user__first_name__istartswith=search_params)
            search |= Q(associate__user__first_name__icontains=search_params)
            search |= Q(associate__contact_phone__istartswith=search_params)

        if is_admin:
            filter_kwargs["is_admin"] = bool(int(is_admin))

        return (
            AssociateCenterAssignment.objects.filter(
                search,
                center_id=center,
                **filter_kwargs,
            )
            .prefetch_related("created_by")
            .select_related(
                "associate__user",
                "role",
            )
        )

    def perform_create(self, serializer):
        user = self.request.user
        center = self.get_center()
        serializer.save(center=center, created_by=user)


class CenterAssociateRolesListView(BaseListCreateAPIView, CenterViewMeta):
    serializer_class = AssociateRoleSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        center = self.get_center()
        user = self.request.user
        filter_kwargs = {}
        search = Q()
        search_query = self.request.query_params.get("search", "").strip()
        active_param = self.request.query_params.get("active", None)
        if active_param and active_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_param))
        account_type = get_user_account_type(user)
        if account_type == UserType.ASSOCIATE:
            associate = getattr(self.request.user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = associate
        if search_query:
            search |= Q(name__istartswith=search_query)
            search |= Q(name__icontains=search_query)

        return (
            AssociateRole.objects.filter(search, center=center, **filter_kwargs)
            .prefetch_related()
            .select_related("center", "created_by")
        )

    def perform_create(self, serializer):
        serializer.save(center=self.get_center(), created_by=self.request.user)


class CenterUUIDCustomerProfilesView(BaseListCreateAPIView):
    """UUID-path scoped: list/create customer profiles for a center by UUID"""

    serializer_class = CenterCustomerProfileHomeCenterSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_queryset(self):
        filter_kwargs = {}
        search_query = Q()
        user = self.request.user
        search_params = self.request.query_params.get("search", "").strip()
        primary = self.request.query_params.get("primary", None)
        active = self.request.query_params.get("active", None)

        if primary:
            filter_kwargs["is_primary"] = bool(int(primary))
        if active:
            filter_kwargs["customer_profile__customer__user__is_active"] = bool(
                int(active)
            )

        account_type = get_user_account_type(user)
        if account_type == UserType.ASSOCIATE:
            associate = getattr(user, "associate", None)
            centers = Center.objects.filter(associate_assignments__associate=associate)
            filter_kwargs["center__in"] = centers

        if search_params:
            search_query |= Q(customer_profile__first_name__istartswith=search_params)
            search_query |= Q(customer_profile__first_name__icontains=search_params)
            search_query |= Q(customer_profile__customer__user__phone__istartswith=search_params)
            search_query |= Q(customer_profile__customer__contact_email__istartswith=search_params)
            search_query |= Q(customer_profile__customer__contact_email__icontains=search_params)

        return (
            CustomerCenterAssignment.objects.filter(
                search_query, center_id=self.kwargs["pk"], **filter_kwargs
            )
            .select_related(
                "customer_profile__customer__user",
            )
            .prefetch_related(
                "created_by",
                "center",
                Prefetch(
                    "customer_profile__center_assignments",
                    queryset=CustomerCenterAssignment.objects.filter(
                        is_primary=True
                    ).select_related("center"),
                    to_attr="primary_center_assignments",
                ),
            )
        )

    def perform_create(self, serializer):
        serializer.save(center_id=self.kwargs["pk"])
