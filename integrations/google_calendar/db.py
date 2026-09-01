from datetime import datetime

# Depends on the Associate.google_* columns proposed in db.md - not migrated yet.


def update_associate_google_tokens(
    associate, access_token: str, expires_at: datetime, refresh_token: str | None = None
):
    """
    Input:
        associate=<Associate row>,
        access_token="gAAAAABo...new-encrypted..." (already encrypted),
        expires_at=2026-09-01 15:56:00+00:00,
        refresh_token="gAAAAABo...new-encrypted..." or None

    Output: none
    """
    associate.google_access_token = access_token
    associate.google_access_token_expires_at = expires_at
    update_fields = ["google_access_token", "google_access_token_expires_at", "updated_at"]
    if refresh_token is not None:
        associate.google_refresh_token = refresh_token
        update_fields.append("google_refresh_token")
    associate.save(update_fields=update_fields)
