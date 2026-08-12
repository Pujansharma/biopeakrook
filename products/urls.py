from django.urls import path, include

from . import views

urlpatterns = [
    path("providers/", include("products.providers.urls")),
    path("", views.ProductsView.as_view()),
    path("<uuid:pk>/", views.ProductDetailView.as_view()),
    path("<uuid:pk>/allowed-documents/", views.ProductAllowedDocumentsView.as_view()),
]
