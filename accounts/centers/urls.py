from django.urls import path, include

from . import views

urlpatterns = [
    path("", views.CentersView.as_view()),
    path("associate-roles/", include("accounts.centers.associate_roles.urls")),
    path("<uuid:pk>/", views.CenterDetailView.as_view()),
    path("<uuid:pk>/operating-hours/", views.CenterOperatingHoursView.as_view()),
    path("<uuid:pk>/associate-roles/", views.CenterAssociateRolesListView.as_view()),
    path("<uuid:pk>/associates/", views.CenterAssociateListView.as_view()),
    path(
        "<uuid:pk>/customer-profiles/", views.CenterUUIDCustomerProfilesView.as_view()
    ),
    path("<uuid:pk>/services/", include("accounts.centers.services.urls")),
    path("<uuid:pk>/programs/", include("accounts.centers.programs.urls")),
]
