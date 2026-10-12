from appointments.mixins import CenterAppointmentsMixin
from appointments.models import AppointmentException
from appointments.permissions import CenterAppointmentPermission
from appointments.serializers.exceptions import (
    AppointmentExceptionCountSerializer,
    AppointmentExceptionListSerializer,
)
from appointments.utils.constants import ExceptionStatus
from appointments.utils.exceptions import acknowledge_exception
from appointments.utils.metrics import record_exceptions_open
from core.utils.exceptions import get_object_or_404
from core.utils.pagination import BasePageNumberPagination
from core.utils.views.main import BaseGenericAPIView, BaseListAPIView


class AppointmentExceptionMixin(CenterAppointmentsMixin):
    permission_classes = [CenterAppointmentPermission]


class AppointmentExceptionListView(AppointmentExceptionMixin, BaseListAPIView):
    serializer_class = AppointmentExceptionListSerializer
    pagination_class = BasePageNumberPagination
    list_success_message = "Appointment exceptions retrieved."

    def get_queryset(self):
        center = self.get_center()
        status = self.request.query_params.get("status", ExceptionStatus.OPEN)
        if status not in ExceptionStatus.values:
            self.raise_bad_request("Invalid status. Use open or resolved.")
        queryset = (
            AppointmentException.objects.filter(center=center, status=status)
            .select_related(
                "appointment__customer_profile",
                "appointment__service",
                "appointment__care_team",
                "appointment__room",
                "appointment__equipment",
                "appointment__center",
            )
            .prefetch_related(
                "appointment__associate_links__associate",
                "appointment__associate_links__role",
            )
            .order_by("-detected_at")
        )
        return queryset


class AppointmentExceptionCountView(AppointmentExceptionMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        center = self.get_center()
        open_count = AppointmentException.objects.filter(
            center=center,
            status=ExceptionStatus.OPEN,
        ).count()
        record_exceptions_open(center.pk, open_count)
        data = AppointmentExceptionCountSerializer({"open_count": open_count}).data
        return self.send_response("Open exception count retrieved.", data)


class AppointmentExceptionAcknowledgeView(AppointmentExceptionMixin, BaseGenericAPIView):
    def post(self, request, *args, **kwargs):
        center = self.get_center()
        exception = get_object_or_404(
            AppointmentException.objects.filter(
                center=center,
                status=ExceptionStatus.OPEN,
            ).select_related(
                "appointment__customer_profile",
                "appointment__service",
                "appointment__care_team",
                "appointment__room",
                "appointment__equipment",
                "appointment__center",
            ),
            "Exception not found.",
            pk=self.kwargs["pk"],
        )
        acknowledge_exception(exception, request.user)
        data = AppointmentExceptionListSerializer(exception).data
        return self.send_response("Exception acknowledged.", data)
