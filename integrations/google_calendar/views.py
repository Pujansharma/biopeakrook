from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.permissions import AllowAny

from accounts.associates.models import Associate
from accounts.utils.permissions import IsAssociateUser
from core.utils.log import logger
from core.utils.views.main import BaseGenericAPIView
from integrations.google_calendar import google_oauth
from integrations.google_calendar.db import update_associate_google_tokens
from integrations.google_calendar.utils import decrypt, encrypt

ADMIN_FRONTEND_URL = getattr(settings, "ADMIN_FRONTEND_URL", None)


def _frontend_redirect(params: dict):
    return HttpResponseRedirect(f"{ADMIN_FRONTEND_URL}/?{urlencode(params)}")


class GoogleCalendarConnectView(BaseGenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        auth_url = google_oauth.build_auth_url()
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

        try:
            tokens = google_oauth.exchange_code(code)
        except requests.HTTPError:
            self.raise_bad_request("Failed to exchange the authorization code with Google")

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            self.raise_bad_request(
                "Google did not return a refresh token. Disconnect and reconnect to grant access again"
            )

        try:
            google_email = google_oauth.fetch_email(tokens["access_token"])
        except requests.HTTPError:
            self.raise_bad_request("Failed to fetch the connected Google account's email")

        associate = Associate.objects.filter(user__email__iexact=google_email).first()
        if associate is None:
            self.raise_bad_request(
                "No Biopeak Staff account uses this Google account's email. "
                "Connect the same Google account you log into Biopeak with."
            )

        associate.email = google_email
        associate.google_access_token = encrypt(tokens["access_token"])
        associate.google_refresh_token = encrypt(refresh_token)
        associate.google_access_token_expires_at = timezone.now() + timedelta(
            seconds=tokens["expires_in"]
        )
        try:
            with transaction.atomic():
                # Associate.email is unique, evict whoever else currently
                # holds this email so the save below doesn't hit that
                # constraint - same transaction so a failure here can't
                # leave this Google account unclaimed by either associate.
                stale_holder_count = (
                    Associate.objects.filter(email=google_email)
                    .exclude(pk=associate.pk)
                    .update(
                        email=None,
                        google_access_token=None,
                        google_refresh_token=None,
                        google_access_token_expires_at=None,
                    )
                )
                associate.save(
                    update_fields=[
                        "email",
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
            data={"email": google_email, "associate_id": str(associate.pk)},
        )


class GoogleCalendarDisconnectView(BaseGenericAPIView):
    permission_classes = [IsAssociateUser]

    def delete(self, request, *args, **kwargs):
        associate = request.user.associate
        if not associate.google_refresh_token:
            return self.send_response("No Google Calendar connection to disconnect.")

        google_oauth.revoke_token(decrypt(associate.google_refresh_token))

        associate.google_access_token = None
        associate.google_refresh_token = None
        associate.google_access_token_expires_at = None
        associate.save(
            update_fields=[
                "google_access_token",
                "google_refresh_token",
                "google_access_token_expires_at",
                "updated_at",
            ]
        )

        return self.send_response("Google Calendar disconnected.")


class GoogleCalendarRefreshTokenView(BaseGenericAPIView):
    permission_classes = [IsAssociateUser]

    def post(self, request, *args, **kwargs):
        associate = request.user.associate
        if not associate.google_refresh_token:
            self.raise_bad_request("No Google Calendar connection to refresh.")

        try:
            tokens = google_oauth.refresh_access_token(decrypt(associate.google_refresh_token))
        except requests.HTTPError:
            self.raise_bad_request("Failed to refresh the Google Calendar token")

        new_refresh_token = encrypt(tokens["refresh_token"]) if "refresh_token" in tokens else None
        update_associate_google_tokens(
            associate,
            access_token=encrypt(tokens["access_token"]),
            expires_at=timezone.now() + timedelta(seconds=tokens["expires_in"]),
            refresh_token=new_refresh_token,
        )

        return self.send_response("Google Calendar token refreshed.")
