from django.urls import path

from . import views

urlpatterns = [
    path('therapy-programs/', views.CustomerTherapyProgramsView.as_view()),
]
