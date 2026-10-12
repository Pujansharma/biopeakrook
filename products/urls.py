from django.urls import path, include

from . import views

urlpatterns = [
    path("providers/", include("products.providers.urls")),
    path("", views.ProductsView.as_view()),
    path("<uuid:pk>/", views.ProductDetailView.as_view()),
    path("<uuid:pk>/allowed-documents/", views.ProductAllowedDocumentsView.as_view()),
    path("document-categories/", views.DocumentCategoryView.as_view()),
    path("document-categories/<uuid:pk>/", views.DocumentCategoryDetailView.as_view()),
    path(
        "document-categories/<uuid:pk>/assignments/",
        views.DocumentCategoryAssignmentListView.as_view(),
    ),
    path(
        "document-categories/<uuid:pk>/available-document-types/",
        views.DocumentCategoryAvailableDocumentTypesView.as_view(),
    ),
    path(
        "document-categories/<uuid:pk>/link-assignments/",
        views.DocumentCategoryAssignmentLinkView.as_view(),
    ),
]
