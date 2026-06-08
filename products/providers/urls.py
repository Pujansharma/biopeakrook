from django.urls import path

from . import views

urlpatterns = [
    path("", views.ProviderListView.as_view()),
    path("callback-options/", views.ProviderCallbackOptionsView.as_view()),
    path("<uuid:pk>/", views.ProviderDetailView.as_view()),
    path("<uuid:pk>/apis/", views.ProviderAPIListView.as_view()),
]
