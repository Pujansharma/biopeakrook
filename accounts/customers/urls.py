from django.urls import path

from . import views

urlpatterns = [
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
]
