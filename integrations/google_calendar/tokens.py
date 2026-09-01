from datetime import datetime, timedelta

from django.utils import timezone

from integrations.google_calendar import google_oauth
from integrations.google_calendar.db import update_associate_google_tokens
from integrations.google_calendar.utils import decrypt, encrypt

REFRESH_BUFFER = timedelta(minutes=5)

# Depends on the Associate.google_* columns proposed in db.md - not migrated yet.


def is_expired(expires_at: datetime | None):
    """
    Input:
        expires_at=2026-09-01T15:00:00+00:00
        (called with `associate.google_access_token_expires_at`; current time
        assumed to be 2026-09-01T14:56:00+00:00, i.e. 4 minutes before expiry)

    Output:
        True - within the 5-minute REFRESH_BUFFER, so treated as expired.
        Also True whenever `expires_at` is None.
    """
    if expires_at is None:
        return True
    return timezone.now() >= expires_at - REFRESH_BUFFER


def get_valid_access_token(associate):
    """
    Returns a usable access token for `associate`, refreshing it first if
    it's expired or about to be.

    Input:
        associate = <Associate row with encrypted google_access_token,
                     encrypted google_refresh_token,
                     google_access_token_expires_at=2026-09-01T14:50:00+00:00>
        (already expired relative to "now")

    Internal call made when expired - google_oauth.refresh_access_token(...):
        Input:  refresh_token="1//0gLp..." (decrypted)
        Output: {"access_token": "ya29.new...", "expires_in": 3599, "token_type": "Bearer"}

    Side effect:
        Persists the new (encrypted) access token, its expiry, and - if
        Google rotated it - the new refresh token via
        `db.update_associate_google_tokens()`.

    Output:
        "ya29.new..." - a plaintext access token ready to use in an
        `Authorization: Bearer <token>` header for calendar_api.py calls.
    """
    if not is_expired(associate.google_access_token_expires_at):
        return decrypt(associate.google_access_token)

    tokens = google_oauth.refresh_access_token(decrypt(associate.google_refresh_token))

    new_refresh_token = encrypt(tokens["refresh_token"]) if "refresh_token" in tokens else None
    update_associate_google_tokens(
        associate,
        access_token=encrypt(tokens["access_token"]),
        expires_at=timezone.now() + timedelta(seconds=tokens["expires_in"]),
        refresh_token=new_refresh_token,
    )

    return tokens["access_token"]
