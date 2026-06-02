from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from accounts.utils.auth import authenticate, get_user_model
from accounts.utils.db import (
    get_password_reset_token_for_user,
    validate_password_reset_token,
)
from accounts.utils.emails import send_reset_password_email
from accounts.verifications.models import TOTPCredential, TOTPSession
from accounts.verifications.utils import verify_two_factor_code
from accounts.verifications.utils.helper import (
    apply_totp_lockout,
    get_registration_code,
)
from core.utils.authentication import perform_login_for_user, get_mfa_token_for_user
from core.utils.serializers import BaseSerializer

User = get_user_model()


class BasePasswordCheckSerializer(BaseSerializer):
    password1 = serializers.CharField(
        max_length=50, min_length=6, label="Password", required=True, write_only=True
    )
    password2 = serializers.CharField(
        max_length=50,
        min_length=6,
        label="Confirm password",
        required=True,
        write_only=True,
    )

    def validate(self, attrs):
        password1 = attrs.get("password1")
        password2 = attrs.get("password2")
        if password1 is not None and password1 != password2:
            raise serializers.ValidationError(_("Passwords do not match."))
        if not password1:
            raise serializers.ValidationError({"password1": "This field is required"})

        try:
            validate_password(password1)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return attrs


class BasePasswordCheckOptionalSerializer(BaseSerializer):
    password1 = serializers.CharField(
        max_length=50, min_length=6, label="Password", required=False, write_only=True
    )
    password2 = serializers.CharField(
        max_length=50,
        min_length=6,
        label="Confirm password",
        required=False,
        write_only=True,
    )
    send_password_link = serializers.BooleanField(required=False, write_only=True)

    @classmethod
    def get_validated_password(cls, attrs):
        password1 = attrs.pop("password1", None)
        password2 = attrs.pop("password2", None)
        if password1 is not None and password1 != password2:
            raise serializers.ValidationError(_("Passwords do not match."))
        if not password1:
            raise serializers.ValidationError({"password1": "This field is required"})
        try:
            validate_password(password1)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return password1


class TOTPAuthenticationMixin:
    mfa_error_messages = {
        "mfa_permanently_locked": _(
            "Account is locked due to multiple failed attempts, contact admin."
        ),
        "mfa_locked": _("Account is temporarily locked, try again later."),
    }

    def check_totp_lockout(self, totp_instance: TOTPCredential) -> None:
        if totp_instance.is_permanently_locked:
            raise AuthenticationFailed(
                self.mfa_error_messages["mfa_permanently_locked"]
            )
        if (
            totp_instance.lock_expires_at
            and totp_instance.lock_expires_at > timezone.now()
        ):
            raise AuthenticationFailed(self.mfa_error_messages["mfa_locked"])

    @staticmethod
    def build_login_response(
        *,
        totp_enabled=False,
        totp_token=None,
        tokens=None,
    ):
        if not tokens:
            tokens = dict()
        access = tokens.get("access")
        refresh = tokens.get("refresh")
        output = {
            "totp_enabled": totp_enabled,
            "totp_token": totp_token,
            "access": access,
            "refresh": refresh,
        }
        return output


class LoginSerializer(TOTPAuthenticationMixin, BaseSerializer):
    email = serializers.EmailField(min_length=3, required=True)
    password = serializers.CharField(max_length=50, min_length=6, write_only=True)

    default_error_messages = {
        "no_active_account": _("No active account found with the given credentials"),
    }

    def validate(self, attrs):
        email = attrs.get("email", None)
        password = attrs.get("password", None)

        user = authenticate(email=email, password=password)
        if not user:
            raise AuthenticationFailed(self.error_messages["no_active_account"])
        totp_instance = TOTPCredential.objects.filter(
            user=user, is_enrolled=True
        ).first()

        is_mfa_required = totp_instance is not None

        if not is_mfa_required:
            return self.build_login_response(tokens=perform_login_for_user(user))

        self.check_totp_lockout(totp_instance)

        return self.build_login_response(
            totp_enabled=True,
            totp_token=get_mfa_token_for_user(user),
        )


class PasswordChangeSerializer(BasePasswordCheckSerializer):
    password = serializers.CharField(max_length=50, label=_("Current password"))

    def validate(self, attrs):
        password = attrs.get("password")
        email = self.context.get("email")
        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError(_("Old password entered incorrectly."))
        passwords = super().validate(attrs)
        user.set_password(passwords.get("password2"))
        user.save()
        return user.email


class RequestPasswordResetEmailSerializer(BaseSerializer):
    email = serializers.EmailField(min_length=2)

    class Meta:
        model = User
        fields = ("email",)

    @classmethod
    def get_user(cls, email):
        """Given an email, return matching user who should receive a reset.

        This allows subclasses to more easily customize the default policies
        that prevent inactive users and users with unusable passwords from
        resetting their password.
        """
        user = User.objects.filter(
            **{"email__iexact": email, "is_active": True}
        ).first()
        if user and user.has_usable_password():
            return user
        return None

    def validate(self, attrs):
        email = attrs.get("email")
        user = self.get_user(email)
        if not user:
            return attrs
        uid, token = get_password_reset_token_for_user(user)
        relative_link = f"/reset-password?uid={uid}&token={token}"
        total_url = settings.PASSWORD_BASE_URL + relative_link
        send_reset_password_email(reset_link=total_url, email=email)
        attrs.update({"email": email, "uid": uid, "token": token, "exists": True})
        return attrs


class PasswordTokenCheckSerializer(BaseSerializer):
    token = serializers.CharField(min_length=1, required=True, write_only=True)
    uid = serializers.CharField(min_length=1, required=True, write_only=True)

    class Meta:
        fields = ("uid", "token")

    def validate(self, attrs):
        uid = attrs.get("uid")
        token = attrs.get("token")
        try:
            user, is_valid = validate_password_reset_token(uid, token)
            if not user:
                raise serializers.ValidationError(_("Invalid uid or token."))
            if not is_valid:
                raise serializers.ValidationError(_("The link is expired or invalid."))
            return user.email
        except ValueError:
            raise serializers.ValidationError(_("Invalid password reset link."))


class ResetPasswordSerializer(BasePasswordCheckSerializer):
    token = serializers.CharField(min_length=1, required=True, write_only=True)
    uid = serializers.CharField(min_length=1, required=True, write_only=True)

    class Meta:
        fields = ("password1", "password2", "token", "uid")

    def validate(self, attrs):
        password1 = super().validate(attrs).get("password1")
        try:
            token = attrs.get("token")
            uid = attrs.get("uid")
            user, is_valid = validate_password_reset_token(uid, token)
            if not user:
                raise serializers.ValidationError(
                    _("The associated user does not exist.")
                )
            if not is_valid:
                raise serializers.ValidationError(
                    _("The reset link is invalid or expired.")
                )
            user.set_password(password1)
            user.save()
            email = user.email
        except ValueError:
            raise serializers.ValidationError(_("The reset link is invalid."))

        # send_password_reset_complete_email(email=email)
        return email


class TOTPVerifySerializer(TOTPAuthenticationMixin, BaseSerializer):
    totp_token = serializers.CharField(required=True, write_only=True)
    totp_code = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        totp_token = attrs.get("totp_token")
        totp_code = attrs.get("totp_code")

        totp_session = (
            TOTPSession.objects.select_related("user__totp_credential")
            .filter_active(token=totp_token, expires_at__gte=timezone.now())
            .first()
        )
        if not totp_session:
            raise serializers.ValidationError("Invalid TOTP session")

        totp_credential = totp_session.user.totp_credential

        self.check_totp_lockout(totp_credential)

        secret = totp_credential.secret
        is_code_valid = verify_two_factor_code(secret, totp_code)

        if not is_code_valid:
            apply_totp_lockout(totp_credential)
            raise serializers.ValidationError({"totp_code": "Invalid TOTP code"})

        TOTPCredential.objects.filter(pk=totp_credential.pk).update(
            failed_attempts=0,
            lock_expires_at=None,
            is_permanently_locked=False,
        )
        TOTPSession.objects.filter(pk=totp_session.pk).update(is_active=False)

        return self.build_login_response(
            totp_enabled=False, tokens=perform_login_for_user(user=totp_session.user)
        )


class PasswordCodeCheckSerializer(BaseSerializer):
    code = serializers.CharField(required=True)

    def validate(self, attrs):
        code = attrs.get("code")
        registration_code = get_registration_code(code)
        if not registration_code:
            raise serializers.ValidationError(
                {"code": "This registration link is invalid."}
            )
        return attrs


class PasswordCreateSerializer(BasePasswordCheckSerializer):
    code = serializers.CharField(required=True)

    def validate(self, attrs):
        code = attrs.get("code")
        registration_code = get_registration_code(code)
        if not registration_code:
            raise serializers.ValidationError(
                {"code": "This registration link is invalid."}
            )
        passwords = super().validate(attrs)
        user = registration_code.user
        _password = passwords.get("password1")
        user.set_password(_password)
        user.save()
        return user
