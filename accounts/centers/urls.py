from django.urls import path

from . import views

urlpatterns = [
    path('', views.CentersView.as_view()),

    # Associate-scoped (center from X-Center-ID header)
    path('detail/', views.AssociateCenterDetailView.as_view()),
    path('associate-roles/', views.AssociateCenterRolesListView.as_view()),
    path('associate-roles/<uuid:pk>/', views.AssociateCenterRoleDetailView.as_view()),

    path('associates/', views.AssociateCenterAssociateListView.as_view()),
    path('associates/<uuid:pk>/', views.AssociateCenterAssociateDetailView.as_view()),

    path('rooms/', views.AssociateCenterRoomListView.as_view()),
    path('rooms/<uuid:pk>/', views.AssociateCenterRoomDetailView.as_view()),
    path('rooms/<uuid:pk>/schedules/', views.AssociateCenterRoomScheduleListView.as_view()),

    path('equipments/', views.AssociateCenterEquipmentListView.as_view()),
    path('equipments/<uuid:pk>/', views.AssociateCenterEquipmentDetailView.as_view()),
    path('equipments/<uuid:pk>/schedules/', views.AssociateCenterEquipmentScheduleListView.as_view()),

    # path('services/'),
    # path('services/<uuid:pk>/'),

    # Admin-scoped (center from URL path)
    path('<uuid:pk>/', views.CenterDetailView.as_view()),
    path('<uuid:pk>/operating-hours/', views.CenterOperatingHoursView.as_view()),
    path('<uuid:pk>/associate-roles/', views.CenterAssociateRolesListView.as_view()),
    path('<uuid:pk>/associates/', views.CenterAssociateListView.as_view()),
]
