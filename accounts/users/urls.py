from django.urls import path

from accounts.users import views

app_name = "users"

urlpatterns = [
    path("profile/", views.UserProfileView.as_view(), name="profile"),
]
