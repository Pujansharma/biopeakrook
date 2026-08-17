from django.urls import path

from . import views

urlpatterns = [
    path("", views.AssessmentServiceListView.as_view()),
    path("<uuid:pk>/", views.AssessmentServiceDetailView.as_view()),
    path("<uuid:pk>/centers/", views.AssessmentServiceCentersView.as_view()),
    path("<uuid:pk>/products/", views.AssessmentServiceProductsView.as_view()),
]
