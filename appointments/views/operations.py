from django.core.exceptions import ValidationError as DjangoValidationError

from appointments.mixins import CenterAppointmentsMixin
from appointments.permissions import CenterAppointmentPermission
from appointments.utils.operations import (
    build_operations_bottlenecks,
    build_operations_capacity,
    build_operations_equipment,
    build_operations_overview,
    build_operations_rooms,
    build_operations_staff,
    get_cached_operations,
    parse_operations_date_range,
)
from core.utils.views.main import BaseGenericAPIView


class OperationsMixin(CenterAppointmentsMixin):
    permission_classes = [CenterAppointmentPermission]

    def get_date_range(self):
        try:
            return parse_operations_date_range(self.request.query_params)
        except DjangoValidationError as error:
            self.raise_bad_request(error.messages[0])

    def build_cached_response(self, tab, builder):
        center = self.get_center()
        start_date, end_date = self.get_date_range()
        data = get_cached_operations(
            center,
            start_date,
            end_date,
            tab,
            builder,
        )
        return self.send_response(f"Operations {tab} retrieved.", data)


class OperationsOverviewView(OperationsMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        return self.build_cached_response("overview", build_operations_overview)


class OperationsStaffView(OperationsMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        return self.build_cached_response("staff", build_operations_staff)


class OperationsRoomsView(OperationsMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        return self.build_cached_response("rooms", build_operations_rooms)


class OperationsEquipmentView(OperationsMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        return self.build_cached_response("equipment", build_operations_equipment)


class OperationsBottlenecksView(OperationsMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        return self.build_cached_response(
            "bottlenecks",
            build_operations_bottlenecks,
        )


class OperationsCapacityView(OperationsMixin, BaseGenericAPIView):
    def get(self, request, *args, **kwargs):
        return self.build_cached_response("capacity", build_operations_capacity)
