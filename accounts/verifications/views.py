from core.utils.views import BaseGenericAPIView
from .serializers import RequestOTPSerializer, LoginOTPSerializer


class RequestOTPView(BaseGenericAPIView):
    serializer_class = RequestOTPSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("OTP sent successfully.")


class LoginOTPView(BaseGenericAPIView):
    serializer_class = LoginOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("Login successful.", data=serializer.validated_data)
