from django.urls import path

from . import views

urlpatterns = [
    path("connect/", views.GoogleCalendarConnectView.as_view()),
    path("callback/", views.GoogleCalendarCallbackView.as_view()),
    path("disconnect/", views.GoogleCalendarDisconnectView.as_view()),
]
