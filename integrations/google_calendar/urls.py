from django.urls import path

from . import views

urlpatterns = [
    path("", views.GoogleCalendarStatusView.as_view()),
    path("connect/", views.GoogleCalendarConnectView.as_view()),
    path("callback/", views.GoogleCalendarCallbackView.as_view()),
    path("disconnect/", views.GoogleCalendarDisconnectView.as_view()),
    path("refresh/", views.GoogleCalendarRefreshTokenView.as_view()),
    path("personal/connect/", views.GoogleCalendarPersonalConnectView.as_view()),
    path("sync/", views.GoogleCalendarSyncView.as_view()),
    path("webhook/", views.GoogleCalendarWebhookView.as_view()),
]
