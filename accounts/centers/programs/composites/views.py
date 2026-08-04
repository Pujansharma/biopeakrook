from django.db.models import F, Q, QuerySet, Value
from django.db.models.functions import Concat
from django.utils import timezone

from accounts.centers.models import Center
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, PackagesPermission
from core.utils.db.functions import ExtractPartText
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import BaseListCreateAPIView
from programs.composites.serializers import CompositeProgramSerializer
from programs.composites.views import CompositeProgramViewMeta
from programs.models import CompositeProgram


class CenterCompositeProgramsView(
    BaseListCreateAPIView,
    CompositeProgramViewMeta,
):
    serializer_class = CompositeProgramSerializer
    permission_classes = [IsAdminUser | PackagesPermission]

    def get_center(self) -> Center:
        center_identifier = self.kwargs["pk"]
        centers = Center.objects.filter(is_active=True)
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            centers = centers.filter(
                associate_assignments__associate=self.request.user.associate,
                associate_assignments__is_active=True,
            )
            if str(self.request.center_id) != str(center_identifier):
                self.raise_permission_denied(
                    "X-Center-ID must match the center in the URL."
                )
        return get_object_or_404(
            centers.distinct(),
            "No valid center found with the given ID.",
            pk=center_identifier,
        )

    def get_queryset(self) -> QuerySet[CompositeProgram]:
        center = self.get_center()
        filter_arguments = {}
        search = Q()
        search_query = self.request.query_params.get("search", "").strip()
        active_query = self.request.query_params.get("active")
        expired_query = self.request.query_params.get("expired")

        if active_query in {"0", "1"}:
            filter_arguments["program__is_active"] = bool(int(active_query))

        expired_filters = {
            "1": {"program__expires_at__lt": timezone.localdate()},
            "0": {"program__expires_at__gte": timezone.localdate()},
        }
        if expired_query and expired_query in expired_filters:
            filter_arguments.update(expired_filters[expired_query])

        if search_query:
            search |= Q(full_name__istartswith=search_query)
            search |= Q(national_phone__istartswith=search_query)
            search |= Q(
                program__customer_profile__customer__contact_email__istartswith=search_query
            )
            search |= Q(
                program__customer_profile__customer__contact_email__icontains=search_query
            )

        return (
            self.get_composite_program_queryset(center.pk)
            .annotate(
                full_name=Concat(
                    F("program__customer_profile__first_name"),
                    Value(" "),
                    F("program__customer_profile__last_name"),
                ),
                national_phone=ExtractPartText(
                    F("program__customer_profile__customer__user__phone"),
                    Value("-"),
                    Value("-1"),
                ),
            )
            .filter(
                search,
                Q(program__center=center)
                | Q(program__redeemable_centers=center),
                **filter_arguments,
            )
            .distinct()
        )

    def perform_create(self, serializer) -> None:
        serializer.save(
            center=self.get_center(),
            created_by=self.request.user,
        )
