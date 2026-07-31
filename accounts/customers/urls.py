from django.urls import path, include

from . import views

urlpatterns = [
    path("addresses/", include("accounts.customers.addresses.urls")),
    path("center-assignments/", include("accounts.customers.center_assignments.urls")),
    path("", views.CustomerProfilesListView.as_view()),
    path("account/", views.CustomerAccountProfileView.as_view()),
    path("<uuid:pk>/", views.CustomerProfileDetailView.as_view()),
    path("<uuid:pk>/associates/", views.CustomerAssociateListView.as_view()),
    path(
        "<uuid:pk>/available-associates/",
        views.CustomerAvailableAssociateView.as_view(),
    ),
    path("<uuid:pk>/link-associates/", views.CustomerLinkAssociateView.as_view()),
    path("<uuid:pk>/centers/", views.CustomerCenterListView.as_view()),
    path("<uuid:pk>/available-centers/", views.CustomerAvailableCenterView.as_view()),
    path("<uuid:pk>/link-centers/", views.CustomerCenterLinkView.as_view()),
    path("<uuid:pk>/addresses/", views.CustomerProfileAddressView.as_view()),
    path("<uuid:pk>/features/", views.CustomerProfileFeatureView.as_view()),
]
