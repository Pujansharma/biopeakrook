from django.urls import path

from webhooks.whatsapp.views import WhatsAppWebhookView

urlpatterns = [
    path("", WhatsAppWebhookView.as_view()),
]
