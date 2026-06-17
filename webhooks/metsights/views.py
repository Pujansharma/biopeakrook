from core.utils.views.main import BaseCreateAPIView
from webhooks.metsights.serializers import MetsightsWebhookSerializer


class MetsightsWebhookView(BaseCreateAPIView):
    serializer_class = MetsightsWebhookSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data={"payload": request.data})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.send_response("Webhook received successfully")
