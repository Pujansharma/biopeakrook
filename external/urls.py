from django.urls import path

from . import views

urlpatterns = [
    path("customer-programs/", views.ExternalUserProgramView.as_view()),
    path("customer-programs/summary/", views.ExternalUserProgramSummaryView.as_view()),
    path("customer-programs/<uuid:pk>/", views.ExternalUserProgramDetailView.as_view()),
    path(
        "customer-programs/<uuid:pk>/services/",
        views.ExternalUserProgramServicesListView.as_view(),
    ),
    path(
        "customer-services/<uuid:pk>/",
        views.ExternalUserProgramServiceDetailView.as_view(),
    ),
    path(
        "customer-services/<uuid:pk>/redemption-history/",
        views.ExternalUserProgramServiceRedemptionHistory.as_view(),
    ),
]
