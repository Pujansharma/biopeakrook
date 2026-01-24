from django.urls import path

from . import views

urlpatterns = [
    path('', views.CentersView.as_view()),
    path('<uuid:pk>/', views.CenterDetailView.as_view()),
    path('<uuid:pk>/operating-hours/', views.CenterOperatingHoursView.as_view()),
]
