from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured

from core.utils.log import logger

GOOGLE_CLIENT_ID = getattr(settings, "GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = getattr(settings, "GOOGLE_CLIENT_SECRET", None)
GOOGLE_REDIRECT_URI = getattr(settings, "GOOGLE_REDIRECT_URI", None)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
REQUEST_TIMEOUT = 10  # seconds

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
]

FLOW_SHARED = "shared"
FLOW_PERSONAL = "personal"

OAUTH_STATE_SALT = "integrations.google_calendar.oauth_state"
OAUTH_STATE_MAX_AGE = 600  # seconds - matches how long Google's own code stays valid


def sign_oauth_state(flow: str, user_id: str | None = None):
    # Signed so 'state' can't be tampered with on the round trip through Google
    payload = {"flow": flow}
    if user_id is not None:
        payload["user_id"] = str(user_id)
    return signing.dumps(payload, salt=OAUTH_STATE_SALT)


def unsign_oauth_state(state: str):
    # Raises signing.BadSignature/SignatureExpired on an invalid/expired state.
    return signing.loads(state, salt=OAUTH_STATE_SALT, max_age=OAUTH_STATE_MAX_AGE)


def build_auth_url(state: str):
    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        raise ImproperlyConfigured(
            "GOOGLE_CLIENT_ID / GOOGLE_REDIRECT_URI is not set, cannot build the "
            "Google authorization URL"
        )
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # required to receive a refresh_token
        "prompt": "consent",  # forces Google to issue a refresh_token every time
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str):
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": GOOGLE_REDIRECT_URI,
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        logger.warning(f"Google OAuth code exchange error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token: str):
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        logger.warning(f"Google OAuth token refresh error {response.status_code}: {response.text}")
    response.raise_for_status()
    return response.json()


def fetch_email(access_token: str):
    response = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if not response.ok:
        logger.warning(f"Google OAuth userinfo lookup error {response.status_code}: {response.text}")
    response.raise_for_status()
    email = response.json().get("email")
    if not email:
        raise ValueError("Google userinfo response did not include an email.")
    return email


def is_invalid_grant_error(error: requests.HTTPError):
    response = error.response
    if response is None or response.status_code != 400:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return payload.get("error") == "invalid_grant"


def revoke_token(token: str):
    response = requests.post(REVOKE_URL, data={"token": token}, timeout=REQUEST_TIMEOUT)
    if response.status_code == 400:
        # Google returns 400 when the token is already invalid/expired/revoked,
        # there is nothing left to revoke, so treat this as success.
        return
    if not response.ok:
        logger.warning(f"Google OAuth token revoke error {response.status_code}: {response.text}")
    response.raise_for_status()
