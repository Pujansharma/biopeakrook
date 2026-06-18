from django.urls import path

from . import views

urlpatterns = [
    path("<uuid:pk>/", views.CustomerProfileAddressDetailView.as_view()),
]
