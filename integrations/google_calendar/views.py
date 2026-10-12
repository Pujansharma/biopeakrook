from datetime import timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.permissions import AllowAny

from accounts.utils import get_user_model
from accounts.utils.permissions import IsAdminUser, IsAssociateUser
from core.utils.exceptions import ServiceUnavailable
from core.utils.log import logger
from core.utils.views.main import BaseGenericAPIView
from integrations.google_calendar import google_oauth
from integrations.google_calendar.availability_sync import (
    sync_google_events_to_availability_blocks,
)
from integrations.google_calendar.connections import (
    connection_is_shared_organizer,
    get_google_calendar_connection_for_user,
    google_calendar_connection_is_connected,
    google_calendar_connection_matches_email,
    user_can_disconnect_shared_organizer,
    user_has_active_google_calendar_owner_profile,
)
from integrations.google_calendar.db import (
    deactivate_google_calendar_connection,
    encrypted_stale_refresh_tokens,
    persist_google_calendar_connection,
    revoke_stored_google_refresh_token,
    update_google_calendar_tokens,
)
from integrations.google_calendar.google_sync import GOOGLE_SYNC_ERRORS
from integrations.google_calendar.utils import (
    decrypt,
    encrypt,
    ensure_encryption_configured,
)
from integrations.google_calendar.webhook_channel import (
    ensure_watch_channel_active_or_log,
    find_connection_for_watch_channel,
    stop_watch_channel,
)

User = get_user_model()

ADMIN_FRONTEND_URL = getattr(settings, "ADMIN_FRONTEND_URL", None)
GOOGLE_CALENDAR_ID = getattr(settings, "GOOGLE_CALENDAR_ID", None)
GOOGLE_CALENDAR_STAFF_PERMISSION = IsAdminUser | IsAssociateUser


def _frontend_redirect(params: dict):
    if not ADMIN_FRONTEND_URL:
        raise ImproperlyConfigured(
            "ADMIN_FRONTEND_URL is not set; cannot redirect to the frontend."
        )
    # Use a URL fragment (#) so these values are not sent to the server
    return HttpResponseRedirect(f"{ADMIN_FRONTEND_URL}/#{urlencode(params)}")


def exchange_google_tokens(code: str):
    # Shared by both connect flows in /callback/.
    tokens = google_oauth.exchange_code(code)
    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in")
    refresh_token = tokens.get("refresh_token")
    if not access_token or not expires_in:
        raise ValueError("Google returned an unexpected token response.")
    if not refresh_token:
        raise ValueError(
            "Google did not return a refresh token. Disconnect and reconnect to grant access again"
        )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": timezone.now() + timedelta(seconds=expires_in),
    }


def resolve_oauth_state(state: str | None):
    if not state:
        raise ValueError("Invalid Google Calendar connection attempt.")
    try:
        return google_oauth.unsign_oauth_state(state)
    except signing.SignatureExpired:
        raise ValueError(
            "This Google Calendar connection attempt has expired. Please try connecting again."
        )
    except signing.BadSignature:
        raise ValueError("Invalid Google Calendar connection attempt.")


def complete_google_calendar_connection(
    user,
    google_email,
    access_token,
    refresh_token,
    expires_at,
):
    try:
        with transaction.atomic():
            return persist_google_calendar_connection(
                user,
                google_email,
                access_token,
                refresh_token,
                expires_at,
            )
    except IntegrityError:
        connection = get_google_calendar_connection_for_user(user)
        if google_calendar_connection_matches_email(connection, google_email):
            return 0
        with transaction.atomic():
            return persist_google_calendar_connection(
                user,
                google_email,
                access_token,
                refresh_token,
                expires_at,
            )


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
            auth_url = google_oauth.build_auth_url(
                state=google_oauth.sign_oauth_state(google_oauth.FLOW_SHARED)
            )
        except ImproperlyConfigured as error:
            raise ServiceUnavailable(str(error))
        return self.send_response(
            "Google Calendar authorization URL generated.",
            data={"auth_url": auth_url},
        )


def _persist_connection(user, google_email, tokens):
    # Returns None on success, or a user-facing error message string.
    stale_refresh_tokens = encrypted_stale_refresh_tokens(google_email, user.pk)
    try:
        stale_holder_count = complete_google_calendar_connection(
            user,
            google_email,
            encrypt(tokens["access_token"]),
            encrypt(tokens["refresh_token"]),
            tokens["expires_at"],
        )
    except IntegrityError:
        connection = get_google_calendar_connection_for_user(user)
        if not google_calendar_connection_matches_email(connection, google_email):
            return "This Google account was just connected by another account. Try again."
        stale_holder_count = 0
    for stale_refresh_token in stale_refresh_tokens:
        revoke_stored_google_refresh_token(stale_refresh_token)
    if stale_holder_count:
        logger.warning(
            f"Google Calendar connect: {google_email} was linked to another "
            f"user; reassigning it to user {user.pk}."
        )
    return None


def _start_personal_watch_channel(user):
    connection = get_google_calendar_connection_for_user(user)
    ensure_watch_channel_active_or_log(connection)
    try:
        sync_google_events_to_availability_blocks(user, connection)
    except GOOGLE_SYNC_ERRORS as error:
        logger.warning(
            f"Google Calendar connect: first availability sync failed for user "
            f"{user.pk}: {error}"
        )


def _complete_shared_connection(google_email: str):
    if not GOOGLE_CALENDAR_ID or google_email.lower() != GOOGLE_CALENDAR_ID.lower():
        return (
            "This is not the shared Google Calendar account used for "
            "appointment sync. Connect the configured shared account instead.",
            None,
        )
    user = User.objects.filter(email__iexact=google_email, is_active=True).first()
    if user is None or not user_has_active_google_calendar_owner_profile(user):
        return (
            "No active Biopeak admin or staff account uses this Google "
            "account's email. Connect the same Google account you log "
            "into Biopeak with.",
            None,
        )
    return None, user


def _complete_personal_connection(user_id: str | None, google_email: str):
    # Target user comes from signed `state`, since /callback/ has no request.user.
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if user is None:
        return "Invalid Google Calendar connection attempt.", None
    if GOOGLE_CALENDAR_ID and google_email.lower() == GOOGLE_CALENDAR_ID.lower():
        return (
            "This Google account is reserved for the shared appointment "
            "calendar. Connect a different personal Google account.",
            None,
        )
    if google_email.lower() != user.email.lower():
        return "Connect the same Google account you log into Biopeak with.", None
    return None, user


class GoogleCalendarCallbackView(BaseGenericAPIView):
    # Handles both connect flows; exchanges the code and redirects with a plain outcome flag.
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        code = request.query_params.get("code")
        state = request.query_params.get("state")

        try:
            relay = resolve_oauth_state(state)
        except ValueError as error:
            return _frontend_redirect({"gcal_error": str(error)})

        if not code:
            return _frontend_redirect(
                {"gcal_error": "Connecting Google Calendar was cancelled or failed."}
            )

        if not google_oauth.GOOGLE_CLIENT_SECRET:
            return _frontend_redirect(
                {"gcal_error": "Google Calendar isn't configured. Contact support."}
            )

        try:
            ensure_encryption_configured()
            tokens = exchange_google_tokens(code)
            google_email = google_oauth.fetch_email(tokens["access_token"])
        except requests.HTTPError:
            return _frontend_redirect(
                {"gcal_error": "Failed to exchange the authorization code with Google."}
            )
        except (ValueError, ImproperlyConfigured) as error:
            return _frontend_redirect({"gcal_error": str(error)})

        flow = relay.get("flow")
        if flow == google_oauth.FLOW_SHARED:
            error, user = _complete_shared_connection(google_email)
        elif flow == google_oauth.FLOW_PERSONAL:
            error, user = _complete_personal_connection(relay.get("user_id"), google_email)
        else:
            error, user = "Invalid Google Calendar connection attempt.", None

        if error is None:
            error = _persist_connection(user, google_email, tokens)

        if error:
            return _frontend_redirect({"gcal_error": error})
        if flow == google_oauth.FLOW_PERSONAL:
            _start_personal_watch_channel(user)
        return _frontend_redirect({"gcal_connected": "1"})


class GoogleCalendarPersonalConnectView(BaseGenericAPIView):
    # Per-user "connect your own Google Calendar" flow, not tied to the shared organizer account.
    permission_classes = [GOOGLE_CALENDAR_STAFF_PERMISSION]

    def post(self, request, *args, **kwargs):
        if not ADMIN_FRONTEND_URL or not google_oauth.GOOGLE_CLIENT_SECRET:
            raise ServiceUnavailable(
                "ADMIN_FRONTEND_URL/GOOGLE_CLIENT_SECRET is not set, cannot start a "
                "Google Calendar connection"
            )
        try:
            auth_url = google_oauth.build_auth_url(
                state=google_oauth.sign_oauth_state(
                    google_oauth.FLOW_PERSONAL, user_id=request.user.pk
                )
            )
        except ImproperlyConfigured as error:
            raise ServiceUnavailable(str(error))
        return self.send_response(
            "Google Calendar authorization URL generated.",
            data={"auth_url": auth_url},
        )


class GoogleCalendarSyncView(BaseGenericAPIView):
    permission_classes = [GOOGLE_CALENDAR_STAFF_PERMISSION]

    def post(self, request, *args, **kwargs):
        connection = get_google_calendar_connection_for_user(request.user)
        if not google_calendar_connection_is_connected(connection):
            self.raise_bad_request("Connect Google Calendar before syncing.")
        if connection_is_shared_organizer(connection):
            self.raise_bad_request(
                "This account is the shared Google Calendar connection used "
                "for appointment sync across all centers. It cannot also be "
                "used for personal calendar sync."
            )

        ensure_watch_channel_active_or_log(connection)

        try:
            summary = sync_google_events_to_availability_blocks(request.user, connection)
        except GOOGLE_SYNC_ERRORS as error:
            logger.warning(
                f"Google Calendar availability sync failed for user "
                f"{request.user.pk}: {error}"
            )
            self.raise_bad_request(
                "Failed to sync Google Calendar. If this keeps happening, "
                "disconnect and reconnect Google Calendar."
            )

        return self.send_response("Google Calendar sync completed.", data=summary)


class GoogleCalendarDisconnectView(BaseGenericAPIView):
    permission_classes = [GOOGLE_CALENDAR_STAFF_PERMISSION]

    def delete(self, request, *args, **kwargs):
        connection = get_google_calendar_connection_for_user(request.user)
        if not google_calendar_connection_is_connected(connection):
            return self.send_response("No Google Calendar connection to disconnect.")

        is_shared_organizer = connection_is_shared_organizer(connection)
        if is_shared_organizer and not user_can_disconnect_shared_organizer(
            request.user
        ):
            self.raise_permission_denied(
                "This account is the shared Google Calendar connection used for "
                "appointment sync across all centers. Only an active platform "
                "admin or center admin can disconnect it."
            )

        stop_watch_channel(connection)

        try:
            google_oauth.revoke_token(decrypt(connection.google_refresh_token))
        except InvalidToken:
            logger.warning(
                f"Google Calendar disconnect: stored token for user "
                f"{request.user.pk} could not be decrypted; clearing it without "
                "revoking with Google."
            )
        except requests.RequestException as error:
            logger.error(
                f"Google Calendar disconnect: Google did not confirm the "
                f"token revoke for user {request.user.pk}: {error}. Not "
                "clearing the local connection so this can be retried."
            )
            ensure_watch_channel_active_or_log(connection)
            raise ServiceUnavailable(
                "Failed to reach Google to revoke the Google Calendar "
                "connection. Please try again."
            ) from error

        deactivate_google_calendar_connection(connection)

        return self.send_response("Google Calendar disconnected")


class GoogleCalendarRefreshTokenView(BaseGenericAPIView):
    permission_classes = [GOOGLE_CALENDAR_STAFF_PERMISSION]

    def post(self, request, *args, **kwargs):
        connection = get_google_calendar_connection_for_user(request.user)
        if not google_calendar_connection_is_connected(connection):
            self.raise_bad_request("No Google Calendar connection to refresh.")

        try:
            refresh_token = decrypt(connection.google_refresh_token)
        except InvalidToken:
            deactivate_google_calendar_connection(connection)
            self.raise_bad_request(
                "Stored Google Calendar token could not be decrypted. "
                "Reconnect Google Calendar to grant access again."
            )

        try:
            tokens = google_oauth.refresh_access_token(refresh_token)
        except requests.HTTPError as error:
            if google_oauth.is_invalid_grant_error(error):
                deactivate_google_calendar_connection(connection)
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
        update_google_calendar_tokens(
            connection,
            access_token=encrypt(access_token),
            expires_at=timezone.now() + timedelta(seconds=expires_in),
            refresh_token=new_refresh_token,
        )

        return self.send_response("Google Calendar token refreshed.")


class GoogleCalendarStatusView(BaseGenericAPIView):
    permission_classes = [GOOGLE_CALENDAR_STAFF_PERMISSION]

    def get(self, request, *args, **kwargs):
        connection = get_google_calendar_connection_for_user(request.user)
        google_email = connection.google_email if connection is not None else None
        is_connected = google_calendar_connection_is_connected(connection)
        last_synced_at = connection.last_synced_at if connection is not None else None
        return self.send_response(
            "Google Calendar connection status.",
            data={
                "google_email": google_email,
                "is_connected": is_connected,
                "last_synced_at": last_synced_at,
            },
        )


class GoogleCalendarWebhookView(BaseGenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        channel_id = request.headers.get("X-Goog-Channel-ID")
        resource_id = request.headers.get("X-Goog-Resource-ID")
        resource_state = request.headers.get("X-Goog-Resource-State")

        connection = find_connection_for_watch_channel(channel_id, resource_id)
        if connection is None:
            logger.warning(
                f"Google Calendar webhook: unrecognized channel {channel_id!r}."
            )
            return self.send_response("Ignored.")

        if resource_state == "sync":
            # Google's initial handshake when the channel is created, not a
            # change notification, so nothing to sync yet.
            return self.send_response("Channel confirmed.")

        try:
            sync_google_events_to_availability_blocks(connection.user, connection)
        except GOOGLE_SYNC_ERRORS as error:
            logger.warning(
                f"Google Calendar webhook: sync failed for user "
                f"{connection.pk}: {error}"
            )

        return self.send_response("Google Calendar webhook processed.")
