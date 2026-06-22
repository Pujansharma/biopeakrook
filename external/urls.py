from django.urls import path

from . import views

urlpatterns = [
    path("customer-therapy-programs/", views.ExternalUserProgramView.as_view()),
    path(
        "customer-therapy-programs/summary/",
        views.ExternalUserProgramSummaryView.as_view(),
    ),
    path(
        "customer-therapy-programs/<uuid:pk>/",
        views.ExternalUserProgramDetailView.as_view(),
    ),
    path(
        "customer-therapy-programs/<uuid:pk>/services/",
        views.ExternalUserProgramServicesListView.as_view(),
    ),
    path(
        "customer-therapy-services/<uuid:pk>/",
        views.ExternalUserProgramServiceDetailView.as_view(),
    ),
    path(
        "customer-therapy-services/<uuid:pk>/redemption-history/",
        views.ExternalUserProgramServiceRedemptionHistory.as_view(),
    ),
    path("customer-associates/", views.ExternalCustomerAssociateListView.as_view()),

    # Notifications
    path("customer-notifications/register/", views.CustomerFirebaseTokenView.as_view()),
]
