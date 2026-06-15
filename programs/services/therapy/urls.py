from django.urls import path

from . import views

urlpatterns = [
    path("", views.TherapyServicesListView.as_view()),
    path("<uuid:pk>/", views.TherapyServicesDetailView.as_view()),
    path("<uuid:pk>/redeem/", views.TherapyServiceRedeemView.as_view()),
    path("<uuid:pk>/cancel/", views.ProgramServiceCancelView.as_view()),
    path(
        "<uuid:pk>/redemption-history/",
        views.ProgramServiceRedemptionHistory.as_view(),
    ),
]
