from django.urls import path

from . import views

urlpatterns = [
    path('therapy-programs/', views.CustomerTherapyProgramsView.as_view()),
    path(
        "therapy-programs/<uuid:program_pk>/services/",
        views.CustomerTherapyProgramServicesView.as_view(),
    ),
    path("composite-programs/", views.CustomerCompositeProgramsView.as_view()),
    path(
        "composite-program-services/",
        views.CustomerCompositeProgramServicesView.as_view(),
    ),
]
