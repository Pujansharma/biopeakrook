from datetime import datetime

from integrations.models import GoogleCalendarConnection


def get_or_create_google_calendar_connection(user):
    connection = GoogleCalendarConnection.objects.filter(user=user).first()
    if connection is not None:
        return connection
    return GoogleCalendarConnection.objects.create(user=user)


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


def evict_google_calendar_email(google_email, exclude_pk):
    return (
        GoogleCalendarConnection.objects.filter(google_email__iexact=google_email)
        .exclude(pk=exclude_pk)
        .update(
            google_email=None,
            google_access_token=None,
            google_refresh_token=None,
            google_access_token_expires_at=None,
        )
    )
