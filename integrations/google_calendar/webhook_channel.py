import uuid
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.utils.log import logger
from integrations.google_calendar import calendar_api
from integrations.google_calendar.availability_sync import (
    sync_google_events_to_availability_blocks,
)
from integrations.google_calendar.connections import connection_is_shared_organizer
from integrations.google_calendar.db import (
    clear_google_calendar_watch_channel,
    persist_google_calendar_watch_channel,
)
from integrations.google_calendar.google_sync import GOOGLE_SYNC_ERRORS
from integrations.google_calendar.tokens import get_valid_access_token
from integrations.models import GoogleCalendarConnection


WATCH_TTL = timedelta(days=30)  # Google's maxbound for a channel is 30 days
RENEWAL_THRESHOLD = timedelta(days=1)
WEBHOOK_BASE_URL = "https://api.biopeak.com"
WEBHOOK_PATH = "google-calendar/webhook/"


def webhook_address() -> str:
    return f"{WEBHOOK_BASE_URL}/{WEBHOOK_PATH}"


def watch_channel_expires_soon(connection) -> bool:
    if not connection.watch_channel_id or not connection.watch_expires_at:
        return True
    return timezone.now() >= connection.watch_expires_at - RENEWAL_THRESHOLD


def find_connection_for_watch_channel(channel_id: str | None, resource_id: str | None):
    if not channel_id or not resource_id:
        return None
    return GoogleCalendarConnection.objects.filter(
        watch_channel_id=channel_id, watch_resource_id=resource_id, is_active=True,
    ).first()


def stop_channel_at_google(connection, channel_id, resource_id):
    # Best-effort: disconnect/reconnect must succeed even if Google can't be
    # reached - a channel that's never stopped just expires on its own.
    if not channel_id or not resource_id:
        return
    try:
        access_token = get_valid_access_token(connection)
        calendar_api.stop_channel(access_token, channel_id, resource_id)
    except GOOGLE_SYNC_ERRORS as error:
        logger.warning(
            f"Google Calendar watch: failed to stop channel "
            f"{channel_id} for user {connection.pk}: {error}"
        )


def stop_watch_channel(connection):
    stop_channel_at_google(
        connection, connection.watch_channel_id, connection.watch_resource_id
    )
    clear_google_calendar_watch_channel(connection)


def start_watch_channel(connection):
    channel_id = str(uuid.uuid4())
    access_token = get_valid_access_token(connection)
    watch = calendar_api.watch_events(
        access_token, channel_id, webhook_address(), WATCH_TTL,
    )
    expires_at = timezone.localtime(
        datetime.fromtimestamp(int(watch["expiration"]) / 1000, tz=UTC)
    )
    persist_google_calendar_watch_channel(
        connection, channel_id, watch["resourceId"], expires_at,
    )


def personal_connections_needing_watch_renewal():
    calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", None)
    queryset = GoogleCalendarConnection.objects.filter(
        is_active=True,
    ).exclude(google_refresh_token__isnull=True).exclude(google_refresh_token="")
    if calendar_id:
        queryset = queryset.exclude(google_email__iexact=calendar_id)

    return queryset.filter(
        Q(watch_channel_id__isnull=True)
        | Q(watch_channel_id="")
        | Q(watch_expires_at__isnull=True)
        | Q(watch_expires_at__lte=timezone.now() + RENEWAL_THRESHOLD)
    )


def ensure_watch_channel_active(connection):
    # The shared appointment calendar is never watched (same rule as the renewal job)
    if connection_is_shared_organizer(connection):
        return
    if not watch_channel_expires_soon(connection):
        return
    old_channel_id = connection.watch_channel_id
    old_resource_id = connection.watch_resource_id
    old_channel_had_expired = bool(
        old_channel_id
        and connection.watch_expires_at
        and connection.watch_expires_at <= timezone.now()
    )

    start_watch_channel(connection)
    stop_channel_at_google(connection, old_channel_id, old_resource_id)
    if old_channel_had_expired:
        # An expired channel left a real gap (pushes were dropped), so catch up now.
        # An early renewal overlaps old and new channels; only a push landing in the
        # instant before the new channel id is saved can be missed (next push/Sync fixes it)
        sync_google_events_to_availability_blocks(connection.user, connection)


def ensure_watch_channel_active_or_log(connection):
    try:
        ensure_watch_channel_active(connection)
    except GOOGLE_SYNC_ERRORS as error:
        logger.warning(
            f"Google Calendar watch: failed to (re)register a notification "
            f"channel for user {connection.pk}: {error}"
        )
