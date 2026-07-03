from django.urls import path

from . import views

urlpatterns = [
    path("", views.UserNotificationListView.as_view()),
    path("register/", views.FirebaseRegistrationView.as_view()),
    path("deregister/", views.FirebaseRegistrationDeregisterView.as_view()),
    path("<uuid:pk>/", views.UserNotificationDetailView.as_view()),
]
