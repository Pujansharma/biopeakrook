from datetime import datetime

import requests
from cryptography.fernet import InvalidToken

from core.utils.log import logger
from integrations.google_calendar import google_oauth
from integrations.google_calendar.utils import decrypt
from integrations.models import GoogleCalendarConnection


def get_or_create_google_calendar_connection(user):
    connection, _created = GoogleCalendarConnection.objects.get_or_create(user=user)
    return connection


def update_google_calendar_tokens(
    connection,
    access_token: str,
    expires_at: datetime,
    refresh_token: str | None = None,
):
    connection.google_access_token = access_token
    connection.google_access_token_expires_at = expires_at
    update_fields = [
        "google_access_token",
        "google_access_token_expires_at",
        "updated_at",
    ]
    if refresh_token is not None:
        connection.google_refresh_token = refresh_token
        update_fields.append("google_refresh_token")
    connection.save(update_fields=update_fields)


def clear_google_calendar_tokens(connection):
    connection.google_access_token = None
    connection.google_refresh_token = None
    connection.google_access_token_expires_at = None
    connection.save(
        update_fields=[
            "google_access_token",
            "google_refresh_token",
            "google_access_token_expires_at",
            "updated_at",
        ]
    )


def revoke_stored_google_refresh_token(encrypted_refresh_token):
    if not encrypted_refresh_token:
        return
    try:
        google_oauth.revoke_token(decrypt(encrypted_refresh_token))
    except InvalidToken:
        return
    except requests.RequestException as error:
        logger.warning(
            f"Google Calendar evict: failed to revoke a stale grant: {error}"
        )


def stale_google_calendar_connections(google_email, exclude_pk):
    return list(
        GoogleCalendarConnection.objects.filter(google_email__iexact=google_email)
        .exclude(pk=exclude_pk)
    )


def revoke_stale_google_calendar_grants(google_email, exclude_pk):
    for connection in stale_google_calendar_connections(google_email, exclude_pk):
        revoke_stored_google_refresh_token(connection.google_refresh_token)


def evict_google_calendar_email(google_email, exclude_pk):
    stale_pks = [
        connection.pk
        for connection in stale_google_calendar_connections(google_email, exclude_pk)
    ]
    if not stale_pks:
        return 0
    return GoogleCalendarConnection.objects.filter(pk__in=stale_pks).update(
        google_email=None,
        google_access_token=None,
        google_refresh_token=None,
        google_access_token_expires_at=None,
    )
