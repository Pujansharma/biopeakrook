from django.urls import path

from webhooks.rook.views import RookDataWebhookView, RookNotificationWebhookView

urlpatterns = [
    path("data/", RookDataWebhookView.as_view(), name="rook-data-webhook"),
    path(
        "notification/",
        RookNotificationWebhookView.as_view(),
        name="rook-notification-webhook",
    ),
]
