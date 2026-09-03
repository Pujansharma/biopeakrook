from django.urls import path, include

from . import views

urlpatterns = [
    path("", views.ServicesView.as_view()),
    path("<uuid:pk>/", views.ServiceDetailView.as_view()),
    path("<uuid:pk>/available-centers/", views.ServiceAvailableCenters.as_view()),
    path("<uuid:pk>/available-products/", views.ServiceAvailableProducts.as_view()),
    path("<uuid:pk>/centers/", views.ServiceCentersView.as_view()),
    path("<uuid:pk>/products/", views.ServiceProductsView.as_view()),

    # Different services
    path("therapy-services/", include("programs.services.therapy.urls")),
    path("assessment-services/", include("programs.services.assessment.urls")),
]
