from core.utils.views import BaseCreateAPIView
from webhooks.strand_genomics.models import StrandGenomicsWebhook


class StrandGenomicsWebhookView(BaseCreateAPIView):
    def post(self, request, *args, **kwargs):
        StrandGenomicsWebhook.objects.create(data=request.data)
        return self.send_response("Webhook received successfully", status=202)
