from django.core import signing

STATE_SALT = "integrations.google_calendar.oauth_state"
STATE_MAX_AGE_SECONDS = 600


def build_state(associate_id):
    """
    Input:  associate_id="3f1c...-uuid-of-the-associate"
    Output: "eyJhc3NvY2lhdGVfaWQiOi...:1a2b3c:xyz..." (opaque to the caller -
        pass it straight into google_oauth.build_auth_url(state=...))
    """
    return signing.dumps({"associate_id": str(associate_id)}, salt=STATE_SALT)


def read_state(state: str):
    """
    Input:  state="eyJhc3NvY2lhdGVfaWQiOi...:1a2b3c:xyz..."
    Output: "3f1c...-uuid-of-the-associate"
    Raises: `django.core.signing.BadSignature` (or its `SignatureExpired`
        subclass, once older than STATE_MAX_AGE_SECONDS).
    """
    payload = signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
    return payload["associate_id"]
