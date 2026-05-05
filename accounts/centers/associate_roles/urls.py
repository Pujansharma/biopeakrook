from django.urls import path
from . import views

urlpatterns = [
    path("<uuid:pk>/", views.AssociateCenterRoleDetailView.as_view()),
]
