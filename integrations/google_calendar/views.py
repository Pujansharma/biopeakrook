from datetime import timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.permissions import AllowAny

from accounts.associates.models import Associate
from accounts.utils.permissions import IsAssociateUser
from core.utils.exceptions import ServiceUnavailable
from core.utils.log import logger
from core.utils.views.main import BaseGenericAPIView
from integrations.google_calendar import google_oauth
from integrations.google_calendar.db import (
    clear_associate_google_tokens,
    update_associate_google_tokens,
)
from integrations.google_calendar.utils import decrypt, encrypt, ensure_encryption_configured

ADMIN_FRONTEND_URL = getattr(settings, "ADMIN_FRONTEND_URL", None)
GOOGLE_CALENDAR_ID = getattr(settings, "GOOGLE_CALENDAR_ID", None)


def _frontend_redirect(params: dict):
    if not ADMIN_FRONTEND_URL:
        raise ImproperlyConfigured(
            "ADMIN_FRONTEND_URL is not set; cannot redirect to the frontend."
        )
    # Use a URL fragment (#) so these values are not sent to the server
    return HttpResponseRedirect(f"{ADMIN_FRONTEND_URL}/#{urlencode(params)}")


class GoogleCalendarConnectView(BaseGenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        if not ADMIN_FRONTEND_URL or not GOOGLE_CALENDAR_ID or not google_oauth.GOOGLE_CLIENT_SECRET:
            raise ServiceUnavailable(
                "ADMIN_FRONTEND_URL/GOOGLE_CALENDAR_ID/GOOGLE_CLIENT_SECRET is "
                "not set, cannot start a Google Calendar connection"
            )
        try:
            auth_url = google_oauth.build_auth_url()
        except ImproperlyConfigured as error:
            raise ServiceUnavailable(str(error))
        return self.send_response(
            "Google Calendar authorization URL generated.",
            data={"auth_url": auth_url},
        )


class GoogleCalendarCallbackView(BaseGenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        code = request.query_params.get("code")
        if not code:
            return _frontend_redirect({"connected": "0", "error": "missing_params"})

        return _frontend_redirect({"code": code})


class GoogleCalendarCompleteView(BaseGenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        code = request.data.get("code")
        if not code:
            self.raise_bad_request("code is required.")
        if not GOOGLE_CALENDAR_ID or not google_oauth.GOOGLE_CLIENT_SECRET:
            raise ServiceUnavailable(
                "GOOGLE_CALENDAR_ID/GOOGLE_CLIENT_SECRET is not set, cannot "
                "complete a Google Calendar connection"
            )
        try:
            ensure_encryption_configured()
        except ImproperlyConfigured as error:
            raise ServiceUnavailable(str(error))

        try:
            tokens = google_oauth.exchange_code(code)
        except requests.HTTPError:
            self.raise_bad_request("Failed to exchange the authorization code with Google")

        access_token = tokens.get("access_token")
        expires_in = tokens.get("expires_in")
        refresh_token = tokens.get("refresh_token")
        if not access_token or not expires_in:
            self.raise_bad_request("Google returned an unexpected token response.")
        if not refresh_token:
            self.raise_bad_request(
                "Google did not return a refresh token. Disconnect and reconnect to grant access again"
            )

        try:
            google_email = google_oauth.fetch_email(access_token)
        except (requests.HTTPError, ValueError):
            self.raise_bad_request("Failed to fetch the connected Google account's email")

        if google_email.lower() != GOOGLE_CALENDAR_ID.lower():
            self.raise_bad_request(
                "This is not the shared Google Calendar account used for "
                "appointment sync. Connect the configured shared account instead."
            )

        associate = Associate.objects.filter(
            user__email__iexact=google_email, is_active=True, user__is_active=True
        ).first()
        if associate is None:
            self.raise_bad_request(
                "No active Biopeak Staff account uses this Google account's email. "
                "Connect the same Google account you log into Biopeak with."
            )

        associate.google_email = google_email
        associate.google_access_token = encrypt(access_token)
        associate.google_refresh_token = encrypt(refresh_token)
        associate.google_access_token_expires_at = timezone.now() + timedelta(
            seconds=expires_in
        )
        try:
            with transaction.atomic():
                # Associate.google_email is unique (case-insensitively), evict
                # whoever else currently holds this email so the save below
                # doesn't hit that constraint - same transaction so a failure
                # here can't leave this Google account unclaimed by either
                # associate.
                stale_holder_count = (
                    Associate.objects.filter(google_email__iexact=google_email)
                    .exclude(pk=associate.pk)
                    .update(
                        google_email=None,
                        google_access_token=None,
                        google_refresh_token=None,
                        google_access_token_expires_at=None,
                    )
                )
                associate.save(
                    update_fields=[
                        "google_email",
                        "google_access_token",
                        "google_refresh_token",
                        "google_access_token_expires_at",
                        "updated_at",
                    ]
                )
        except IntegrityError:
            self.raise_bad_request(
                "This Google account was just connected by another associate. Try again."
            )
        if stale_holder_count:
            logger.warning(
                f"Google Calendar connect: {google_email} was linked to another "
                f"associate; reassigning it to associate {associate.pk}."
            )

        return self.send_response(
            "Google Calendar connected.",
            data={"google_email": google_email, "associate_id": str(associate.pk)},
        )


class GoogleCalendarDisconnectView(BaseGenericAPIView):
    permission_classes = [IsAssociateUser]

    def delete(self, request, *args, **kwargs):
        associate = request.user.associate
        if not associate.google_refresh_token:
            return self.send_response("No Google Calendar connection to disconnect.")

        is_shared_organizer = (
            GOOGLE_CALENDAR_ID
            and associate.google_email
            and associate.google_email.lower() == GOOGLE_CALENDAR_ID.lower()
        )
        if is_shared_organizer and not (
            associate.is_active
            and associate.center_assignments.filter(
                is_admin=True, is_active=True
            ).exists()
        ):
            self.raise_permission_denied(
                "This account is the shared Google Calendar connection used for "
                "appointment sync across all centers. Only an active center "
                "admin can disconnect it."
            )

        try:
            google_oauth.revoke_token(decrypt(associate.google_refresh_token))
        except InvalidToken:
            logger.warning(
                f"Google Calendar disconnect: stored token for associate "
                f"{associate.pk} could not be decrypted; clearing it without "
                f"revoking with Google."
            )
        except requests.RequestException as error:
            logger.error(
                f"Google Calendar disconnect: Google did not confirm the "
                f"token revoke for associate {associate.pk}: {error}. Not "
                f"clearing the local connection so this can be retried."
            )
            raise ServiceUnavailable(
                "Failed to reach Google to revoke the Google Calendar "
                "connection. Please try again."
            ) from error

        clear_associate_google_tokens(associate)

        return self.send_response("Google Calendar disconnected.")


class GoogleCalendarRefreshTokenView(BaseGenericAPIView):
    permission_classes = [IsAssociateUser]

    def post(self, request, *args, **kwargs):
        associate = request.user.associate
        if not associate.google_refresh_token:
            self.raise_bad_request("No Google Calendar connection to refresh.")

        try:
            refresh_token = decrypt(associate.google_refresh_token)
        except InvalidToken:
            clear_associate_google_tokens(associate)
            self.raise_bad_request(
                "Stored Google Calendar token could not be decrypted. "
                "Reconnect Google Calendar to grant access again."
            )

        try:
            tokens = google_oauth.refresh_access_token(refresh_token)
        except requests.HTTPError as error:
            if google_oauth.is_invalid_grant_error(error):
                clear_associate_google_tokens(associate)
                self.raise_bad_request(
                    "Google rejected the stored Google Calendar token. "
                    "Reconnect Google Calendar to grant access again."
                )
            self.raise_bad_request("Failed to refresh the Google Calendar token")

        access_token = tokens.get("access_token")
        expires_in = tokens.get("expires_in")
        if not access_token or not expires_in:
            self.raise_bad_request("Google returned an unexpected token response.")

        refresh_token = tokens.get("refresh_token")
        new_refresh_token = encrypt(refresh_token) if refresh_token else None
        update_associate_google_tokens(
            associate,
            access_token=encrypt(access_token),
            expires_at=timezone.now() + timedelta(seconds=expires_in),
            refresh_token=new_refresh_token,
        )

        return self.send_response("Google Calendar token refreshed.")


class GoogleCalendarStatusView(BaseGenericAPIView):
    permission_classes = [IsAssociateUser]

    def get(self, request, *args, **kwargs):
        associate = request.user.associate
        return self.send_response(
            "Google Calendar connection status.",
            data={
                "google_email": associate.google_email,
                "is_connected": bool(associate.google_refresh_token),
            },
        )
