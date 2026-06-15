from django.urls import path

from accounts.centers.programs.therapy import views

# Prefixed with /centers/:center_id/programs/
urlpatterns = [
    # list/create programs per center.
    path("", views.CenterTherapyProgramsView.as_view()),
]
