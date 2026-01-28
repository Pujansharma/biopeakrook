from django.urls import path

from . import views

urlpatterns = [
    path('', views.CentersView.as_view()),
    path('<uuid:pk>/', views.CenterDetailView.as_view()),
    path('<uuid:pk>/operating-hours/', views.CenterOperatingHoursView.as_view()),
    path('<uuid:pk>/associate-roles/', views.CenterAssociateRolesListView.as_view()),
    path('<uuid:pk>/associates/', views.CenterAssociateListView.as_view()),
]
