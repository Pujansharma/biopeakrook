from datetime import datetime, timedelta

import requests
from django.utils import timezone

from integrations.google_calendar import google_oauth
from integrations.google_calendar.db import (
    clear_google_calendar_tokens,
    update_google_calendar_tokens,
)
from integrations.google_calendar.utils import decrypt, encrypt

REFRESH_BUFFER = timedelta(minutes=5)


def is_expired(expires_at: datetime | None):
    if expires_at is None:
        return True
    return timezone.now() >= expires_at - REFRESH_BUFFER


def get_valid_access_token(connection):
    if not connection.google_refresh_token:
        raise ValueError(
            f"User {connection.pk} has no connected Google Calendar account."
        )

    if not is_expired(connection.google_access_token_expires_at):
        return decrypt(connection.google_access_token)

    connection.refresh_from_db(
        fields=[
            "google_refresh_token",
            "google_access_token",
            "google_access_token_expires_at",
        ]
    )
    if not connection.google_refresh_token:
        raise ValueError(
            f"User {connection.pk} has no connected Google Calendar account."
        )
    if not is_expired(connection.google_access_token_expires_at):
        return decrypt(connection.google_access_token)

    try:
        tokens = google_oauth.refresh_access_token(
            decrypt(connection.google_refresh_token)
        )
    except requests.HTTPError as error:
        if google_oauth.is_invalid_grant_error(error):
            clear_google_calendar_tokens(connection)
        raise

    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in")
    if not access_token or not expires_in:
        raise ValueError("Google returned an unexpected token response.")

    refresh_token = tokens.get("refresh_token")
    new_refresh_token = encrypt(refresh_token) if refresh_token else None
    update_google_calendar_tokens(
        connection,
        access_token=encrypt(access_token),
        expires_at=timezone.now() + timedelta(seconds=expires_in),
        refresh_token=new_refresh_token,
    )

    return access_token
