from django.db.models import Prefetch

from accounts.associates.models import Associate, AssociateCenterAssignment
from accounts.centers.models import Center
from accounts.customers.models import CustomerCenterAssignment
from accounts.utils.constants import UserType
from accounts.utils.db import get_user_account_type
from appointments.models import Appointment, CenterCareTeam, CenterCareTeamMember
from appointments.utils.exceptions import (
    apply_availability_exception_hooks,
    get_source_type_for_instance,
    pick_exception_scan_status,
)
from core.utils.exceptions import get_object_or_404


class CenterAvailabilityMixin:
    """Resolve URL center with tenant checks for availability APIs."""

    def get_center_id(self):
        return self.kwargs["center_id"]

    def get_center(self):
        center_id = self.get_center_id()
        centers = Center.objects.filter(is_active=True)
        if get_user_account_type(self.request.user) == UserType.ASSOCIATE:
            centers = centers.filter(
                associate_assignments__associate=self.request.user.associate,
                associate_assignments__is_active=True,
            )
            header_center_id = getattr(self.request, "center_id", None)
            if header_center_id is None:
                header_center_id = self.request.headers.get("X-Center-ID")
            if str(header_center_id) != str(center_id):
                self.raise_bad_request(
                    "X-Center-ID must match the center in the URL."
                )
        return get_object_or_404(
            centers.distinct(),
            "No valid center found with the given ID.",
            pk=center_id,
        )

    def get_active_query_filter(self):
        filter_kwargs = {}
        active_query = self.request.query_params.get("active")
        if active_query in {"0", "1"}:
            filter_kwargs["is_active"] = bool(int(active_query))
        else:
            filter_kwargs["is_active"] = True
        return filter_kwargs

    def get_associate(self):
        center = self.get_center()
        return get_object_or_404(
            Associate.objects.filter(
                is_active=True,
                center_assignments__center=center,
                center_assignments__is_active=True,
            ).distinct(),
            "Associate not found.",
            pk=self.kwargs["associate_id"],
        )

    def get_care_team(self):
        center = self.get_center()
        return get_object_or_404(
            CenterCareTeam.objects.filter(center=center, is_active=True).prefetch_related(
                Prefetch(
                    "members",
                    queryset=CenterCareTeamMember.objects.select_related(
                        "associate",
                        "role",
                        "care_team",
                    ),
                )
            ),
            "Care team not found.",
            pk=self.kwargs["care_team_id"],
        )


class CenterAppointmentsMixin:
    """Resolve URL center for appointment APIs without X-Center-ID requirement."""

    def get_center_id(self):
        return self.kwargs["center_id"]

    def get_center(self):
        center_id = self.get_center_id()
        centers = Center.objects.filter(is_active=True)
        account_type = get_user_account_type(self.request.user)
        has_associate_profile = hasattr(self.request.user, "associate")
        if account_type == UserType.ASSOCIATE:
            if not has_associate_profile:
                centers = centers.none()
            else:
                centers = centers.filter(
                    pk__in=AssociateCenterAssignment.objects.filter(
                        associate=self.request.user.associate,
                        is_active=True,
                    ).values_list("center_id", flat=True)
                )
        elif account_type == UserType.ADMIN and has_associate_profile:
            active_assignments = AssociateCenterAssignment.objects.filter(
                associate=self.request.user.associate,
                is_active=True,
            )
            if active_assignments.exists():
                centers = centers.filter(
                    pk__in=active_assignments.values_list("center_id", flat=True)
                )
        elif account_type == UserType.CUSTOMER:
            if not hasattr(self.request.user, "customer"):
                centers = centers.none()
            else:
                centers = centers.filter(
                    pk__in=CustomerCenterAssignment.objects.filter(
                        customer_profile__customer=self.request.user.customer,
                        is_active=True,
                    ).values_list("center_id", flat=True)
                )
        return get_object_or_404(
            centers.distinct(),
            "No valid center found with the given ID.",
            pk=center_id,
        )

    def get_appointment_queryset(self):
        return (
            Appointment.objects.filter(center=self.get_center())
            .select_related(
                "customer_profile",
                "service",
                "room",
                "equipment",
                "center",
                "care_team",
            )
            .prefetch_related(
                "associate_links__associate__user",
                "associate_links__role",
            )
        )

    def get_customer_owned_appointment_queryset(self):
        queryset = self.get_appointment_queryset()
        if get_user_account_type(self.request.user) != UserType.CUSTOMER:
            return queryset
        return queryset.filter(customer_profile__customer_id=self.request.user.pk)


class AvailabilityExceptionHooksMixin:
    """Run exception detection/resolution after availability writes."""

    def apply_exception_side_effects(self, instance, validated_data=None, created=False):
        source_type = get_source_type_for_instance(instance)
        if source_type is None:
            return None
        result = apply_availability_exception_hooks(
            center=self.get_center(),
            instance=instance,
            source_type=source_type,
            validated_data=validated_data,
            created=created,
        )
        self._last_exception_scan = result
        return result

    def attach_exception_scan(self, response, scan_results=None):
        if scan_results is None:
            scan_results = [getattr(self, "_last_exception_scan", None)]
        exception_scan = pick_exception_scan_status(scan_results)
        if exception_scan is not None:
            response.data["exception_scan"] = exception_scan
        return response

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self.apply_exception_side_effects(
            serializer.instance,
            serializer.validated_data,
            created=False,
        )

    def patch(self, request, *args, **kwargs):
        self._last_exception_scan = None
        response = super().patch(request, *args, **kwargs)
        return self.attach_exception_scan(response)

    def post(self, request, *args, **kwargs):
        self._last_exception_scan = None
        response = super().post(request, *args, **kwargs)
        return self.attach_exception_scan(response)
