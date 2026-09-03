from django.urls import path

from appointments.views import booking, exceptions, operations

urlpatterns = [
    path("slots/", booking.AppointmentSlotFindView.as_view()),
    path("", booking.AppointmentCollectionView.as_view()),
    path(
        "<uuid:pk>/",
        booking.AppointmentDetailView.as_view(),
    ),
    path(
        "<uuid:pk>/check-in/",
        booking.AppointmentCheckInView.as_view(),
    ),
    path(
        "<uuid:pk>/start/",
        booking.AppointmentStartView.as_view(),
    ),
    path(
        "<uuid:pk>/mark-late/",
        booking.AppointmentMarkLateView.as_view(),
    ),
    path(
        "<uuid:pk>/complete/",
        booking.AppointmentCompleteView.as_view(),
    ),
    path(
        "<uuid:pk>/no-show/",
        booking.AppointmentNoShowView.as_view(),
    ),
    path(
        "<uuid:pk>/cancel/",
        booking.AppointmentCancelView.as_view(),
    ),
    path(
        "<uuid:pk>/reschedule/",
        booking.AppointmentRescheduleView.as_view(),
    ),
    path(
        "exceptions/",
        exceptions.AppointmentExceptionListView.as_view(),
    ),
    path(
        "exceptions/count/",
        exceptions.AppointmentExceptionCountView.as_view(),
    ),
    path(
        "exceptions/<uuid:pk>/acknowledge/",
        exceptions.AppointmentExceptionAcknowledgeView.as_view(),
    ),
    path(
        "operations/overview/",
        operations.OperationsOverviewView.as_view(),
    ),
    path(
        "operations/staff/",
        operations.OperationsStaffView.as_view(),
    ),
    path(
        "operations/rooms/",
        operations.OperationsRoomsView.as_view(),
    ),
    path(
        "operations/equipment/",
        operations.OperationsEquipmentView.as_view(),
    ),
    path(
        "operations/bottlenecks/",
        operations.OperationsBottlenecksView.as_view(),
    ),
    path(
        "operations/capacity/",
        operations.OperationsCapacityView.as_view(),
    ),
]
