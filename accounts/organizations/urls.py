from django.urls import path

from . import views

urlpatterns = [
    path("", views.OrganizationDetailView.as_view()),
    path("summary/", views.OrganizationSummaryView.as_view()),
]
