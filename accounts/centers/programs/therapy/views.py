from django.db.models import F, Prefetch, Q, Value, ExpressionWrapper, BooleanField
from django.db.models.functions import Concat
from django.utils import timezone

from accounts.centers.models import Center
from accounts.customers.models import CustomerCenterAssignment
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.db.functions import ExtractPartText
from core.utils.exceptions import get_object_or_404
from core.utils.views.main import (
    BaseListCreateAPIView,
)
from programs.models import ProgramService, TherapyProgram
from programs.therapy.serializers import TherapyProgramSerializer


class CenterTherapyProgramsView(BaseListCreateAPIView):
    serializer_class = TherapyProgramSerializer
    permission_classes = [IsAdminUser | IsAssociateUser]

    def get_center(self):
        user = self.request.user
        center_id = self.kwargs.get("pk")
        associate_query = Q()
        if get_user_account_type(user) == UserType.ASSOCIATE:
            associate = user.associate
            associate_query = Q(associate_assignments__associate=associate)
        qs = Center.objects.filter(associate_query)
        return get_object_or_404(
            qs, "No valid center found with the given ID", pk=center_id
        )

    def get_queryset(self):
        filter_kwargs = {}
        search = Q()
        associate_query = Q()
        center = self.get_center()
        search_query = self.request.query_params.get("search", "").strip()
        active_query_param = self.request.query_params.get("active", None)
        complete_query = self.request.query_params.get("complete", None)
        expired_query = self.request.query_params.get("expired", None)

        if active_query_param and active_query_param in ["0", "1"]:
            filter_kwargs["is_active"] = bool(int(active_query_param))

        if complete_query and complete_query in ["0", "1"]:
            filter_kwargs["is_complete"] = bool(int(complete_query))

        expired_filter_map = {
            "1": {"program__expires_at__lt": timezone.localdate()},
            "0": {"program__expires_at__gte": timezone.localdate()},
        }
        if expired_query and expired_query in expired_filter_map:
            filter_kwargs.update(expired_filter_map[expired_query])

        if search_query:
            search |= Q(full_name__istartswith=search_query)
            search |= Q(national_phone__istartswith=search_query)
            search |= Q(
                program__customer_profile__customer__contact_email__istartswith=search_query
            )
            search |= Q(
                program__customer_profile__customer__contact_email__icontains=search_query
            )
        qs = (
            TherapyProgram.objects.annotate(
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
                is_complete=ExpressionWrapper(
                    Q(sessions_count=F("sessions_used") + F("sessions_cancelled")),
                    output_field=BooleanField(),
                ),
            )
            .filter(
                search,
                Q(Q(program__redeemable_centers=center) | Q(program__center=center)),
                associate_query,
                **filter_kwargs,
            )
            .select_related(
                "program",
                "program__center",
                "program__created_by",
                "program__customer_profile__customer__user",
            )
            .prefetch_related(
                Prefetch(
                    "program__program_services",
                    queryset=ProgramService.objects.select_related(
                        "service", "created_by", "therapy_service"
                    ),
                ),
                "program__redeemable_centers",
                Prefetch(
                    "program__customer_profile__center_assignments",
                    queryset=CustomerCenterAssignment.objects.filter(
                        is_primary=True
                    ).select_related("center"),
                    to_attr="primary_center_assignments",
                ),
            )
            .distinct()
        )
        return qs

    def perform_create(self, serializer):
        serializer.save(
            center_id=self.kwargs.get("pk"),
            created_by=self.request.user,
        )
