from core.utils.views import BaseRetrieveAPIView


class HomePageView(BaseRetrieveAPIView):
    def get(self, request, *args, **kwargs):
        return self.send_response("OK")
