from django.urls import path

from . import views

urlpatterns = [
    path("", views.AssociateView.as_view()),
    path("profile/", views.AssociateProfileView.as_view()),
    path("permissions/", views.AssociatePermissionView.as_view()),
    path("<uuid:pk>/", views.AssociateDetailView.as_view()),
    # Center assignments for associates
    path("<uuid:pk>/centers/", views.AssociateAssignedCenters.as_view()),
    path("<uuid:pk>/available-centers/", views.AssociateAvailableCenterView.as_view()),
    path("<uuid:pk>/link-centers/", views.AssociateCenterLinkView.as_view()),
    # Customer Profiles for Associates
    path("<uuid:pk>/profiles/", views.AssociateLinkedProfilesView.as_view()),
    path(
        "<uuid:pk>/available-profiles/", views.AssociateAvailableProfilesView.as_view()
    ),
    path("<uuid:pk>/link-profiles/", views.AssociateLinkProfileView.as_view()),
]
