from django.urls import path

from . import views

urlpatterns = [
    path("", views.AssessmentServiceListSerializer.as_view())
]
