from django.urls import path

from accounts import views
from accounts.verifications.views import RequestOTPView, LoginOTPView, ValidateTOTPView

app_name = "accounts"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.BaseTokenRefreshView.as_view(), name="refresh"),
    path(
        "change-password/", views.PasswordChangeView.as_view(), name="change_password"
    ),
    path(
        "forgot-password/",
        views.RequestPasswordResetEmailView.as_view(),
        name="forgot_password",
    ),
    path(
        "check-password-token/",
        views.PasswordTokenCheckView.as_view(),
        name="check_password_token",
    ),
    path("reset-password/", views.ResetPasswordView.as_view(), name="reset_password"),
    # OTP Flow
    path("request-otp/", RequestOTPView.as_view(), name="request_otp"),
    path("login-otp/", LoginOTPView.as_view(), name="login_otp"),
    path("verify-totp/", ValidateTOTPView.as_view()),
]
