from django.urls import path

from . import views

urlpatterns = [
    path("connect/", views.GoogleCalendarConnectView.as_view()),
    path("callback/", views.GoogleCalendarCallbackView.as_view()),
    path("complete/", views.GoogleCalendarCompleteView.as_view()),
    path("disconnect/", views.GoogleCalendarDisconnectView.as_view()),
    path("refresh/", views.GoogleCalendarRefreshTokenView.as_view()),
]
