from datetime import datetime, timedelta

from integrations.google_calendar import google_oauth
from integrations.google_calendar.utils import decrypt, encrypt, now_ist

REFRESH_BUFFER = timedelta(minutes=5)


def is_expired(expires_at: datetime | None) -> bool:
    """
    Checks whether a stored access token is expired, or close enough to expiring
    that it should be refreshed before use.

    Input:
        expires_at=2026-09-01T15:00:00+05:30
        (called with `connection.access_token_expires_at`; current time assumed
        to be 2026-09-01T14:56:00+05:30, i.e. 4 minutes before expiry)

    Output:
        True — within the 5-minute REFRESH_BUFFER, so treated as expired.
        Also True whenever `expires_at` is None (token was never issued/stored).
    """
    if expires_at is None:
        return True
    return now_ist() >= expires_at - REFRESH_BUFFER


def get_valid_access_token(connection) -> str:
    """
    Returns a usable access token for `connection`, refreshing it first if it's
    expired or about to be. `connection` is whatever model row ends up storing
    access_token/refresh_token/access_token_expires_at (encrypted at rest) per
    associate — that model isn't defined in this folder yet.

    Input:
        connection = <row with encrypted access_token="gAAAAA...",
                       encrypted refresh_token="gAAAAA...",
                       access_token_expires_at=2026-09-01T14:50:00+05:30>
        (already expired relative to "now")

    Internal call made when expired — google_oauth.refresh_access_token(...):
        Input:  refresh_token="1//0gLp..." (decrypted)
        Output: {"access_token": "ya29.new...", "expires_in": 3599, "token_type": "Bearer"}

    Side effect:
        connection.access_token = encrypt("ya29.new...")
        connection.access_token_expires_at = now + 3599 seconds
        connection.save()

    Output:
        "ya29.new..." — a plaintext access token ready to use in an
        `Authorization: Bearer <token>` header for calendar_api.py calls.
    """
    if not is_expired(connection.access_token_expires_at):
        return decrypt(connection.access_token)

    tokens = google_oauth.refresh_access_token(decrypt(connection.refresh_token))

    connection.access_token = encrypt(tokens["access_token"])
    connection.access_token_expires_at = now_ist() + timedelta(seconds=tokens["expires_in"])
    if "refresh_token" in tokens:
        connection.refresh_token = encrypt(tokens["refresh_token"])
    connection.save()

    return tokens["access_token"]
