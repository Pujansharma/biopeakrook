from django.urls import path

from . import views

# Prefixed with /centers/:center_id/programs/
urlpatterns = [
    # list/create programs per center.
    path("", views.CenterProgramsView.as_view()),
]
