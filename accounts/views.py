from pygments.styles import default
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView

from accounts.serializers import (
    PasswordChangeSerializer,
    ResetPasswordSerializer,
    PasswordTokenCheckSerializer,
    RequestPasswordResetEmailSerializer,
    LoginSerializer,
    PasswordCreateSerializer,
    PasswordCodeCheckSerializer,
)
from core.utils.view_types import PostMethodMixin
from core.utils.views import BaseGenericAPIView


class BaseTokenRefreshView(TokenRefreshView, BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint for refreshing an access token"""

    def post(self, request, *args, **kwargs):
        resp = super().post(request, *args, **kwargs)
        return self.send_response(detail="Token refreshed.", data=resp.data)


class LoginView(TokenObtainPairView, BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint for login"""

    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        resp = super().post(request, *args, **kwargs)
        return self.send_response(detail="Login successful.", data=resp.data)


class PasswordChangeView(BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint for changing password while logged in"""

    serializer_class = PasswordChangeSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Both request.user.email and self.request.user.email will have proper typing
        user_email = request.user.email  # Now this should have proper typing too
        serializer = self.get_serializer(
            data=request.data, context={"email": user_email}
        )
        serializer.is_valid(raise_exception=True)
        return self.send_response(detail="Password changed successfully.")


class RequestPasswordResetEmailView(BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint for requesting a password reset link in registered email"""

    serializer_class = RequestPasswordResetEmailSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response("Request received, you shall receive a link shortly.")


class PasswordTokenCheckView(BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint for checking the token passed in the email"""

    serializer_class = PasswordTokenCheckSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response(detail="Token is valid.")


class ResetPasswordView(BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint for resetting the password using token"""

    serializer_class = ResetPasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response(detail="Password reset successful.")


class CheckPasswordCodeView(BaseGenericAPIView, PostMethodMixin):
    serializer_class = PasswordCodeCheckSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response(detail="Code is valid")


class SetPasswordView(BaseGenericAPIView, PostMethodMixin):
    """Standard endpoint to set a password using token"""

    serializer_class = PasswordCreateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.send_response(detail="Password set successfully")
