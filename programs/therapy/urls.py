from django.urls import path

from . import views

urlpatterns = [
    path("services/", views.TherapyProgramServicesView.as_view()),
    path("<uuid:pk>/", views.TherapyProgramDetailView.as_view()),
    path(
        "<uuid:pk>/services/",
        views.TherapyProgramServicesListView.as_view(),
    ),
    path("<uuid:pk>/redeem/", views.TherapyProgramRedeemView.as_view()),
    path(
        "<uuid:pk>/cancel/",
        views.TherapyProgramCancelView.as_view(),
    ),
]
