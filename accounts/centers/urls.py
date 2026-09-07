from django.urls import path, include

from . import views

urlpatterns = [
    path("", views.CentersView.as_view()),
    path("associates/", include("accounts.centers.associates.urls")),
    path("associate-roles/", include("accounts.centers.associate_roles.urls")),
    path("<uuid:pk>/", views.CenterDetailView.as_view()),
    path("<uuid:pk>/operating-hours/", views.CenterOperatingHoursView.as_view()),
    path("<uuid:pk>/associate-roles/", views.CenterAssociateRolesListView.as_view()),
    path("<uuid:pk>/associates/", views.CenterAssociateListView.as_view()),
    path(
        "<uuid:pk>/customer-profiles/", views.CenterUUIDCustomerProfilesView.as_view()
    ),
    path("<uuid:pk>/services/", include("accounts.centers.services.urls")),
    path("<uuid:pk>/v2/", include("accounts.centers.v2.urls")),
    path("<uuid:center_id>/availability/", include("appointments.urls")),
    path("<uuid:center_id>/appointments/", include("appointments.booking_urls")),
    path("<uuid:center_id>/care-teams/", include("appointments.care_team_urls")),
    path(
        "<uuid:pk>/therapy-programs/", include("accounts.centers.programs.therapy.urls")
    ),
    path(
        "<uuid:pk>/composite-programs/",
        include("accounts.centers.programs.composites.urls"),
    ),
]
