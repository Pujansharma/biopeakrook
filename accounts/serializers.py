from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from accounts.utils.auth import authenticate, get_user_model
from accounts.utils.db import get_password_reset_token_for_user, validate_password_reset_token
from accounts.utils.emails import send_reset_password_email
from core.utils.authentication import perform_login_for_user
from core.utils.serializers import BaseSerializer

User = get_user_model()


class BasePasswordCheckSerializer(BaseSerializer):
    password1 = serializers.CharField(
        max_length=50, min_length=6, label="Password", required=True, write_only=True
    )
    password2 = serializers.CharField(
        max_length=50, min_length=6, label="Confirm password", required=True, write_only=True
    )

    def validate(self, attrs):
        password1 = attrs.get('password1')
        password2 = attrs.get('password2')
        if password1 is not None and password1 != password2:
            raise serializers.ValidationError(_("Passwords do not match."))
        try:
            validate_password(password1)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return attrs


class LoginSerializer(BaseSerializer):
    email = serializers.EmailField(min_length=3, required=True)
    password = serializers.CharField(max_length=50, min_length=6, write_only=True)

    default_error_messages = {
        "no_active_account": _("No active account found with the given credentials"),
    }

    def validate(self, attrs):
        email = attrs.get('email', None)
        password = attrs.get('password', None)
        user = authenticate(email=email, password=password)
        if not user:
            raise AuthenticationFailed(self.error_messages["no_active_account"])
        return perform_login_for_user(user)


class PasswordChangeSerializer(BasePasswordCheckSerializer):
    password = serializers.CharField(max_length=50, label=_("Current password"))

    def validate(self, attrs):
        password = attrs.get('password')
        email = self.context.get('email')
        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError(_("Old password entered incorrectly."))
        passwords = super().validate(attrs)
        user.set_password(passwords.get('password2'))
        user.save()
        return user.email


class RequestPasswordResetEmailSerializer(BaseSerializer):
    email = serializers.EmailField(min_length=2)

    class Meta:
        model = User
        fields = ('email',)

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
        email = attrs.get('email')
        user = self.get_user(email)
        if not user:
            raise serializers.ValidationError(_("Email not registered, link cannot be sent."))
        uid, token = get_password_reset_token_for_user(user)
        relative_link = f"/reset-password?uid={uid}&token={token}"
        total_url = settings.PASSWORD_RESET_URL + relative_link
        send_reset_password_email(reset_link=total_url, email=email)
        attrs.update({'email': email, 'uid': uid, 'token': token, 'exists': True})
        return attrs


class PasswordTokenCheckSerializer(BaseSerializer):
    token = serializers.CharField(min_length=1, required=True, write_only=True)
    uid = serializers.CharField(min_length=1, required=True, write_only=True)

    class Meta:
        fields = ('uid', 'token')

    def validate(self, attrs):
        uid = attrs.get('uid')
        token = attrs.get('token')
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
        fields = ('password1', 'password2', 'token', 'uid')

    def validate(self, attrs):
        password1 = super().validate(attrs).get('password1')
        try:
            token = attrs.get('token')
            uid = attrs.get('uid')
            user, is_valid = validate_password_reset_token(uid, token)
            if not user:
                raise serializers.ValidationError(_("The associated user does not exist."))
            if not is_valid:
                raise serializers.ValidationError(_('The reset link is invalid or expired.'))
            user.set_password(password1)
            user.save()
            email = user.email
        except ValueError:
            raise serializers.ValidationError(_("The reset link is invalid."))

        # send_password_reset_complete_email(email=email)
        return email
