from accounts.serializers import TOTPVerifySerializer
from core.utils.views.main import BaseCreateAPIView
from .serializers import RequestOTPSerializer, LoginOTPSerializer, VerifyOTPSerializer


class RequestOTPView(BaseCreateAPIView):
    serializer_class = RequestOTPSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("OTP sent successfully.")


class LoginOTPView(BaseCreateAPIView):
    serializer_class = LoginOTPSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("Login successful.", data=serializer.validated_data)


class VerifyOTPView(BaseCreateAPIView):
    serializer_class = VerifyOTPSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response(
            "Verification successful.", data=serializer.validated_data
        )


class ValidateTOTPView(BaseCreateAPIView):
    serializer_class = TOTPVerifySerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response(
            "Verification successful.", data=serializer.validated_data
        )
