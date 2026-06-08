from core.utils.views import BaseCreateAPIView
from webhooks.bugspeaks.models import BugspeaksWebhook


class BugspeaksWebhookView(BaseCreateAPIView):
    def post(self, request, *args, **kwargs):
        BugspeaksWebhook.objects.create(data=request.data)
        return self.send_response("Webhook received successfully", status=202)
