from django.urls import path

from appointments.views import booking

urlpatterns = [
    path(
        "customer-appointments/<uuid:customer_profile_id>/",
        booking.AppointmentCustomerAppointmentsListView.as_view(),
    ),
]
