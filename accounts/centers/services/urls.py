from django.urls import path

from . import views

urlpatterns = [
    path("", views.CenterAssignedServiceView.as_view()),
]
