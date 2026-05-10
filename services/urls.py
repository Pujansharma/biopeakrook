from django.urls import path

from . import views

urlpatterns = [
    path("", views.ServicesView.as_view()),
    path("<uuid:pk>/", views.ServiceDetailView.as_view()),
    path("<uuid:pk>/available-centers/", views.ServiceAvailableCenters.as_view()),
    path("program-services/", views.ProgramServicesListView.as_view()),
    path("program-services/<uuid:pk>/redeem/", views.ServiceRedeemView.as_view()),
    path(
        "program-services/<uuid:pk>/cancel/", views.ProgramServiceCancelView.as_view()
    ),
    path(
        "program-services/<uuid:pk>/redemption-history/",
        views.ProgramServiceRedemptionHistory.as_view(),
    ),
]
