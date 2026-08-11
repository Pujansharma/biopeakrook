from django.urls import path

from accounts.centers.programs.composites import views

urlpatterns = [
    path("", views.CenterCompositeProgramsView.as_view()),
]
