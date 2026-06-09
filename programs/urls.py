from django.urls import path

from . import views

urlpatterns = [
    path("wellness-programs/<uuid:pk>/", views.WellnessProgramDetailView.as_view()),
    path(
        "wellness-programs/<uuid:pk>/services/",
        views.WellnessProgramServicesListView.as_view(),
    ),
    path(
        "wellness-programs/<uuid:pk>/cancel/",
        views.WellnessProgramCancelView.as_view(),
    ),
    path(
        "wellness-programs/<uuid:pk>/redeem/", views.WellnessProgramRedeemView.as_view()
    ),
]
