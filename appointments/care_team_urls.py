from django.urls import path

from appointments.views.care_teams import (
    CenterCareTeamDetailView,
    CenterCareTeamListCreateView,
)

urlpatterns = [
    path("", CenterCareTeamListCreateView.as_view()),
    path("<uuid:pk>/", CenterCareTeamDetailView.as_view()),
]
