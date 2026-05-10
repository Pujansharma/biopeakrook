from django.urls import path

from . import views

urlpatterns = [
    path("", views.AdminUserView.as_view()),
    path("profile/", views.AdminProfileView.as_view()),
    path("<uuid:pk>/", views.AdminUserDetailView.as_view()),
]
