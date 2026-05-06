from django.urls import path

from . import views

urlpatterns = [
    path("equipments/", views.AssociateCenterEquipmentListView.as_view()),
    path("equipments/<uuid:pk>/", views.AssociateCenterEquipmentDetailView.as_view()),
    path(
        "equipments/<uuid:pk>/schedules/",
        views.AssociateCenterEquipmentScheduleListView.as_view(),
    ),
]
