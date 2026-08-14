from django.urls import path

from webhooks.orange_labs.views import OrangeLabsWebhookView

urlpatterns = [
    path("", OrangeLabsWebhookView.as_view()),
]
