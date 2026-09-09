from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from integrations.communications.outbox import process_whatsapp_webhook_payload
from integrations.communications.whatsapp.signature import (
    verify_whatsapp_webhook_signature,
)


class WhatsAppWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        verify_token = getattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", None) or ""
        if mode == "subscribe" and token and token == verify_token and challenge:
            return HttpResponse(challenge, content_type="text/plain", status=200)
        return HttpResponse("Forbidden", status=403)

    def post(self, request, *args, **kwargs):
        app_secret = getattr(settings, "WHATSAPP_APP_SECRET", None) or ""
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        if not verify_whatsapp_webhook_signature(
            body=request.body,
            signature_header=signature_header,
            app_secret=app_secret,
        ):
            return HttpResponse("Invalid signature", status=403)

        process_whatsapp_webhook_payload(request.data)
        return HttpResponse("EVENT_RECEIVED", status=200)
