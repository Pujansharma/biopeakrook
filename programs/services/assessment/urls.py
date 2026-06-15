from django.urls import path

from . import views

urlpatterns = [
    path("", views.AssessmentServiceListView.as_view()),
    path("<uuid:pk>/", views.AssessmentServiceDetailView.as_view()),
    path("<uuid:pk>/centers/", views.AssessmentServiceDetailView.as_view()),
]
