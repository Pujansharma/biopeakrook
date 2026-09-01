from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.signing import BadSignature
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.permissions import AllowAny

from accounts.associates.models import Associate
from accounts.utils.permissions import IsAssociateUser
from core.utils.log import logger
from core.utils.views.main import BaseGenericAPIView
from integrations.google_calendar import google_oauth
from integrations.google_calendar.state import build_state, read_state
from integrations.google_calendar.utils import decrypt, encrypt

# Depends on the Associate.google_* columns proposed in db.md, not migrated yet.

ADMIN_FRONTEND_URL = getattr(settings, "ADMIN_FRONTEND_URL", None)


def _frontend_redirect(params: dict):
    return HttpResponseRedirect(f"{ADMIN_FRONTEND_URL}/?{urlencode(params)}")


class GoogleCalendarConnectView(BaseGenericAPIView):
    """
    Returns Google's consent-screen URL for the signed-in associate. The
    frontend navigates the browser there itself.
    """

    permission_classes = [IsAssociateUser]

    def get(self, request, *args, **kwargs):
        state = build_state(request.user.associate.pk)
        auth_url = google_oauth.build_auth_url(state=state)
        return self.send_response(
            "Google Calendar authorization URL generated.",
            data={"auth_url": auth_url},
        )


class GoogleCalendarCallbackView(BaseGenericAPIView):
    """
    Google redirects the staff member's browser back here after consent.
    Unauthenticated - the associate is identified via `state` (see
    `state.py`), not via a client-supplied id. Always redirects back to the
    admin frontend, success or failure.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        state = request.query_params.get("state")
        code = request.query_params.get("code")
        if not state or not code:
            return _frontend_redirect({"connected": "0", "error": "missing_params"})

        try:
            associate_id = read_state(state)
        except BadSignature:
            return _frontend_redirect({"connected": "0", "error": "invalid_state"})

        associate = Associate.objects.filter(pk=associate_id).first()
        if associate is None:
            return _frontend_redirect({"connected": "0", "error": "associate_not_found"})

        try:
            tokens = google_oauth.exchange_code(code)
        except requests.HTTPError:
            return _frontend_redirect({"connected": "0", "error": "exchange_failed"})

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return _frontend_redirect({"connected": "0", "error": "no_refresh_token"})

        try:
            google_email = google_oauth.fetch_email(tokens["access_token"])
        except requests.HTTPError:
            return _frontend_redirect({"connected": "0", "error": "profile_fetch_failed"})

        associate.google_email = google_email
        associate.google_access_token = encrypt(tokens["access_token"])
        associate.google_refresh_token = encrypt(refresh_token)
        associate.google_access_token_expires_at = timezone.now() + timedelta(
            seconds=tokens["expires_in"]
        )
        try:
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
            logger.warning(
                f"Google Calendar connect: {google_email} is already linked to another associate."
            )
            return _frontend_redirect({"connected": "0", "error": "email_already_connected"})

        return _frontend_redirect({"connected": "1", "email": google_email})


class GoogleCalendarDisconnectView(BaseGenericAPIView):
    """
    Disconnects the signed-in associate's own Google Calendar.
    """

    permission_classes = [IsAssociateUser]

    def delete(self, request, *args, **kwargs):
        associate = request.user.associate
        if not associate.google_refresh_token:
            return self.send_response("No Google Calendar connection to disconnect.")

        google_oauth.revoke_token(decrypt(associate.google_refresh_token))

        associate.google_email = None
        associate.google_access_token = None
        associate.google_refresh_token = None
        associate.google_access_token_expires_at = None
        associate.save(
            update_fields=[
                "google_email",
                "google_access_token",
                "google_refresh_token",
                "google_access_token_expires_at",
                "updated_at",
            ]
        )

        return self.send_response("Google Calendar disconnected.")
