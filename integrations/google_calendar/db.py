from datetime import datetime


def update_associate_google_tokens(
    associate, access_token: str, expires_at: datetime, refresh_token: str | None = None
):
    associate.google_access_token = access_token
    associate.google_access_token_expires_at = expires_at
    update_fields = ["google_access_token", "google_access_token_expires_at", "updated_at"]
    if refresh_token is not None:
        associate.google_refresh_token = refresh_token
        update_fields.append("google_refresh_token")
    associate.save(update_fields=update_fields)
