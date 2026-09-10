from django.urls import path

from accounts.centers.v2 import views

urlpatterns = [
    path("room-types/", views.RoomTypeListCreateView.as_view()),
    path("room-types/<uuid:type_id>/", views.RoomTypeDetailView.as_view()),
    path("equipment-types/", views.EquipmentTypeListCreateView.as_view()),
    path("equipment-types/<uuid:type_id>/", views.EquipmentTypeDetailView.as_view()),
    path("rooms/", views.RoomListCreateView.as_view()),
    path("rooms/<uuid:room_id>/", views.RoomDetailView.as_view()),
    path("equipments/", views.EquipmentListCreateView.as_view()),
    path("equipments/<uuid:equipment_id>/", views.EquipmentDetailView.as_view()),
    path("services/", views.CenterServiceV2ListView.as_view()),
    path("services/<uuid:service_id>/", views.CenterServiceV2DetailView.as_view()),
]
