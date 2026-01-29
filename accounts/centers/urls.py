from django.urls import path

from . import views

urlpatterns = [
    path('', views.CentersView.as_view()),

    # Associate-scoped (center from X-Center-ID header)
    path('associate-roles/', views.AssociateCenterRolesListView.as_view()),
    path('associate-roles/<uuid:pk>/', views.AssociateCenterRoleDetailView.as_view()),

    path('associates/', views.AssociateCenterAssociateListView.as_view()),
    path('associates/<uuid:pk>/', views.AssociateCenterAssociateDetailView.as_view()),

    # Admin-scoped (center from URL path)
    path('<uuid:pk>/', views.CenterDetailView.as_view()),
    path('<uuid:pk>/operating-hours/', views.CenterOperatingHoursView.as_view()),
    path('<uuid:pk>/associate-roles/', views.CenterAssociateRolesListView.as_view()),
    path('<uuid:pk>/associates/', views.CenterAssociateListView.as_view()),
]
