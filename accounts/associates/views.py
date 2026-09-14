from django.db.models import (
    Exists,
    F,
    OuterRef,
    Prefetch,
    ProtectedError,
    Q,
    RestrictedError,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, Concat

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.associates.serializers import (
    AdminAssociateSerializer,
    AdminAssociateCenterLinkSerializer,
    AssociateCenterSerializer,
    CenterAssignmentAssociateProfileSerializer,
    AssociateCenterPermissionSerializer,
    AssociateLinkedProfileSerializer,
    AssociateAvailableProfileSerializer,
    AssociateProfileLinkSerializer,
    AdminAssociateDetailSerializer,
)
from accounts.centers.models import Center
from accounts.centers.serializers import AssociateAvailableCenterSerializer
from accounts.customers.models import CustomerAssociateAssignment, CustomerProfile
from accounts.organizations.utils.db import decrement_organization_admins_count
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import (
    IsAdminUser,
    AssociateAdminPermission,
    AssociateFeaturePermission,
    IsAssociateUser,
)
from core.utils.db.functions import ExtractPartText
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListCreateAPIView,
    BaseRetrieveUpdateDestroyAPIView,
    BaseCreateAPIView,
    BaseListAPIView,
    BaseRetrieveUpdateAPIView,
    BaseRetrieveAPIView,
)


class AssociateView(BaseListCreateAPIView):
    """Endpoint to create and list all associates"""

    permission_classes = [IsAdminUser]
    serializer_class = AdminAssociateSerializer

    def get_queryset(self):
        filter_kwargs = {}
        search_query = Q()
        search_params = self.request.query_params.get("search", "").strip()
        active_param = self.request.query_params.get("active", None)
        admin_query = self.request.query_params.get("admin", None)
        care_staff_query = self.request.query_params.get("care_staff", None)
        center_code_query = self.request.query_params.getlist('center_code', [])
        center_codes = list(filter(None, center_code_query))
        if active_param and active_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_param))

        if admin_query and admin_query in ["0", "1"]:
            admin_mapping = {
                "0": {"center_assignments__is_admin": False},
                "1": {"center_assignments__is_admin": True},
            }
            filter_kwargs.update(admin_mapping[admin_query])
        if care_staff_query and care_staff_query in ["0", "1"]:
            care_staff_mapping = {
                "0": {"center_assignments__is_care_staff": False},
                "1": {"center_assignments__is_care_staff": True},
            }
            filter_kwargs.update(care_staff_mapping[care_staff_query])
        if center_codes:
            filter_kwargs['center_assignments__center__code__in'] = center_codes

        if search_params:
            search_query |= Q(user__email__istartswith=search_params)
            search_query |= Q(national_phone__istartswith=search_params)
            search_query |= Q(full_name__istartswith=search_params)

        return (
            Associate.objects.select_related(
                "user",
            )
            .annotate(
                national_phone=ExtractPartText(
                    F("contact_phone"), Value("-"), Value("-1")
                ),
                full_name=Concat(
                    F("user__first_name"), Value(" "), F("user__last_name")
                ),
            )
            # Intentionally unsliced; the serializer limits the preview to three.
            .prefetch_related(
                Prefetch(
                    "center_assignments",
                    queryset=AssociateCenterAssignment.objects.select_related(
                        "center"
                    ).order_by("-created_at"),
                )
            )
            .filter(search_query, **filter_kwargs)
            .order_by("-created_at")
            .distinct()
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AssociateDetailView(BaseRetrieveUpdateDestroyAPIView):
    """Endpoint to view details for any associate"""

    permission_classes = [IsAdminUser]
    serializer_class = AdminAssociateDetailSerializer

    def get_queryset(self):
        return Associate.objects.select_related()

    def perform_destroy(self, instance: Associate):
        user = instance.user
        try:
            user.delete()
            decrement_organization_admins_count()
        except (RestrictedError, ProtectedError) as e:
            restricted_count = len(getattr(e, "restricted_objects", set()))
            protected_count = len(getattr(e, "protected_objects", set()))
            total = restricted_count + protected_count
            self.raise_bad_request(
                f"Cannot delete this associate. {total} related record(s) exist."
            )


class AssociateAvailableCenterView(BaseListAPIView):
    """View to list centers available for any associate"""

    permission_classes = [IsAdminUser]
    serializer_class = AssociateAvailableCenterSerializer

    def get_associate(self):
        associate_id = self.kwargs.get("pk")
        qs = Associate.objects.select_related().filter()
        return get_object_or_404(qs, pk=associate_id)

    def get_queryset(self):
        search_query = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            # Prefix and substring lookups are intentional for instant search.
            search_query |= Q(name__istartswith=search_params)
            search_query |= Q(code__istartswith=search_params)
            search_query |= Q(code__icontains=search_params)
            search_query |= Q(name__icontains=search_params)

        associate = self.get_associate()
        # Separate querysets intentionally distinguish existence from flag values.
        associated_centers_subquery = AssociateCenterAssignment.objects.filter(
            associate=associate, center=OuterRef("pk")
        )
        associate_subquery = AssociateCenterAssignment.objects.filter(
            associate=associate, center=OuterRef("pk")
        )
        return Center.objects.annotate(
            exists=Exists(associated_centers_subquery),
            is_admin=Coalesce(
                Subquery(associate_subquery.values("is_admin")), Value(False)
            ),
            is_care_staff=Coalesce(
                Subquery(associate_subquery.values("is_care_staff")), Value(False)
            ),
        ).filter(search_query).order_by('-exists', '-created_at')


class AssociateCenterLinkView(BaseCreateAPIView):
    """View to link or delink associates to a center"""

    permission_classes = [IsAdminUser]
    serializer_class = AdminAssociateCenterLinkSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get("pk")
        )

    def perform_create(self, serializer):
        associate = self.get_associate()
        serializer.save(associate=associate, created_by=self.request.user)


class AssociateAssignedCenters(BaseListAPIView):
    """List an associate's complete center assignments with pagination."""

    permission_classes = [IsAdminUser]
    serializer_class = AssociateCenterSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        associate = self.get_associate()
        search_query = Q()
        search_params = self.request.query_params.get("search", "").strip()
        if search_params:
            # Prefix and substring lookups are intentional for instant search.
            search_query |= Q(center__name__istartswith=search_params)
            search_query |= Q(center__code__istartswith=search_params)
            search_query |= Q(center__code__icontains=search_params)
            search_query |= Q(center__name__icontains=search_params)

        return (
            AssociateCenterAssignment.objects.select_related("center")
            .filter(search_query, associate=associate)
        )


class AssociateProfileView(BaseRetrieveUpdateAPIView):
    """View for associates to retrieve & update their own profile"""

    permission_classes = [IsAssociateUser]
    serializer_class = CenterAssignmentAssociateProfileSerializer

    def get_center(self):
        center_id = self.request.headers.get("x-center-id")
        qs = Center.objects.filter()
        return get_object_or_404(qs, "No center found with the given ID", pk=center_id)

    def get_queryset(self):
        center = self.get_center()
        return AssociateCenterAssignment.objects.select_related(
            "associate__user__account", "center"
        ).prefetch_related("role_links__role").filter(associate__user=self.request.user, center=center)

    def get_object(self):
        return get_object_or_404(
            self.get_queryset(),
            "Associate assignment not found for this center.",
        )


class AssociatePermissionView(BaseRetrieveAPIView):
    """View for associates to view their own permissions"""

    permission_classes = [
        AssociateAdminPermission | AssociateFeaturePermission | IsAssociateUser
    ]
    serializer_class = AssociateCenterPermissionSerializer

    def get_queryset(self):
        center_id = getattr(self.request, "center_id", None)

        if not center_id:
            self.raise_bad_request("Center ID is not present or invalid.")

        associate = getattr(self.request.user, "associate", None)

        return (
            AssociateCenterAssignment.objects.select_related("associate", "center")
            .prefetch_related("role_links__role")
            .filter(
                associate=associate,
                center__id=center_id,
            )
        )

    def get_object(self):
        return self.get_queryset().first()


class AssociateLinkedProfilesView(BaseListAPIView):
    """List customer profiles linked to an associate."""

    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateLinkedProfileSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        associate = self.get_associate()
        center_id = self.request.query_params.get("center_id", None)
        search_param = self.request.query_params.get("search", "").strip()

        if search_param:
            search |= Q(full_name__istartswith=search_param)
            search |= Q(national_phone__istartswith=search_param)
            search |= Q(
                customer_profile__customer__contact_email__istartswith=search_param
            )
            search |= Q(
                customer_profile__customer__contact_email__icontains=search_param
            )

        if center_id:
            filter_kwargs["center_id"] = center_id

        account_type = get_user_account_type(self.request.user)
        if account_type == UserType.ASSOCIATE:
            request_associate = getattr(self.request.user, "associate", None)
            filter_kwargs["center__associate_assignments__associate"] = (
                request_associate
            )

        return (
            CustomerAssociateAssignment.objects.select_related(
                "customer_profile__customer__user",
            )
            .annotate(
                full_name=Concat(
                    F("customer_profile__first_name"),
                    Value(" "),
                    F("customer_profile__last_name"),
                ),
                national_phone=ExtractPartText(
                    F("customer_profile__customer__user__phone"),
                    Value("-"),
                    Value("-1"),
                ),
            )
            .filter(search, associate=associate, **filter_kwargs)
            .order_by("-created_at")
        )


class AssociateAvailableProfilesView(BaseListAPIView):
    """List customer profiles available to be linked to an associate, scoped by center."""

    permission_classes = [IsAdminUser | IsAssociateUser]
    serializer_class = AssociateAvailableProfileSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get("pk")
        )

    def get_queryset(self):
        search = Q()
        filter_kwargs = {}
        associate = self.get_associate()
        center_id = self.request.query_params.get("center_id", None)
        search_param = self.request.query_params.get("search", "").strip()

        if search_param:
            search |= Q(full_name__istartswith=search_param)
            search |= Q(customer__user__email__istartswith=search_param)

        account_type = get_user_account_type(self.request.user)
        if account_type == UserType.ASSOCIATE:
            request_associate = getattr(self.request.user, "associate", None)
            filter_kwargs[
                "center_assignments__center__associate_assignments__associate"
            ] = request_associate

        if center_id:
            filter_kwargs["center_assignments__center_id"] = center_id

        exists_subquery = CustomerAssociateAssignment.objects.filter(
            associate=associate,
            customer_profile=OuterRef("pk"),
            **({"center_id": center_id} if center_id else {}),
        )

        return (
            CustomerProfile.objects.select_related("customer__user")
            .annotate(
                full_name=Concat(F("first_name"), Value(" "), F("last_name")),
                exists=Exists(exists_subquery),
            )
            .filter(search, is_converted=True, **filter_kwargs)
            .distinct()
            .order_by("-created_at")
        )


class AssociateLinkProfileView(BaseCreateAPIView):
    """Link or unlink customer profiles to an associate at a center."""

    permission_classes = [IsAdminUser]
    serializer_class = AssociateProfileLinkSerializer

    def get_associate(self):
        qs = Associate.objects.select_related()
        return get_object_or_404(
            qs, "Associate with the given ID does not exist", pk=self.kwargs.get("pk")
        )

    def perform_create(self, serializer):
        associate = self.get_associate()
        serializer.save(associate=associate, created_by=self.request.user)
