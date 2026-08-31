from urllib.parse import urlencode

import requests

from integrations.google_calendar import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Narrowest scopes that do the job: read/write events (not whole calendars),
# and the email address, just to label the connection in the UI.
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
]


def build_auth_url(state: str) -> str:
    """
    Builds the URL to redirect the staff member's browser to, so they can approve
    calendar access on Google's consent screen.
    GET https://accounts.google.com/o/oauth2/v2/auth

    Input:
        state="associate:3f1c...-random-csrf-token"
        (an opaque value you generate, stored server-side and verify when the
        callback comes back — protects against CSRF on the OAuth redirect)

    Query params encoded into the URL:
        {
            "client_id": "xxx.apps.googleusercontent.com",
            "redirect_uri": "http://127.0.0.1:8001/auth/google/callback",
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/userinfo.email",
            "access_type": "offline",
            "prompt": "consent",
            "state": "associate:3f1c...-random-csrf-token",
        }

    Output:
        "https://accounts.google.com/o/oauth2/v2/auth?client_id=xxx...&redirect_uri=...&state=..."
        (send the staff member's browser here; nothing to call directly)
    """
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",  # required to receive a refresh_token
        "prompt": "consent",  # forces Google to issue a refresh_token every time
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """
    Trades the one-time authorization code (from the OAuth callback's `?code=`
    query param) for an access token + refresh token.
    POST https://oauth2.googleapis.com/token

    Input:
        code="4/0AY0e-g7...one-time-code-from-callback"

    Request form body:
        {
            "client_id": "xxx.apps.googleusercontent.com",
            "client_secret": "GOCSPX-xxx",
            "code": "4/0AY0e-g7...",
            "grant_type": "authorization_code",
            "redirect_uri": "http://127.0.0.1:8001/auth/google/callback",
        }

    Output (Google's response, returned as-is):
        {
            "access_token": "ya29.a0Af...",
            "refresh_token": "1//0gLp...",
            "expires_in": 3599,
            "scope": "https://www.googleapis.com/auth/calendar.events ...",
            "token_type": "Bearer",
        }
    """
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
        },
    )
    response.raise_for_status()
    return response.json()


def refresh_access_token(refresh_token: str) -> dict:
    """
    Exchanges a stored refresh token for a fresh access token, once the old one
    has expired (or is about to).
    POST https://oauth2.googleapis.com/token

    Input:
        refresh_token="1//0gLp...decrypted-refresh-token"

    Request form body:
        {
            "client_id": "xxx.apps.googleusercontent.com",
            "client_secret": "GOCSPX-xxx",
            "refresh_token": "1//0gLp...",
            "grant_type": "refresh_token",
        }

    Output (Google's response, returned as-is — note: no new refresh_token
    unless Google decides to rotate it, which is why callers check for its
    presence before overwriting the stored one):
        {
            "access_token": "ya29.a0Af...",
            "expires_in": 3599,
            "scope": "https://www.googleapis.com/auth/calendar.events ...",
            "token_type": "Bearer",
        }
    """
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    response.raise_for_status()
    return response.json()


def fetch_email(access_token: str) -> str:
    """
    Looks up the Google account's email address, just to label the connection
    in the UI (e.g. "Connected as priya@gmail.com").
    GET https://www.googleapis.com/oauth2/v2/userinfo

    Input:
        access_token="ya29.a0Af..."

    Request headers: {"Authorization": "Bearer ya29.a0Af..."}

    Output:
        "priya@gmail.com"
        (extracted from Google's response, e.g. {"email": "priya@gmail.com", "id": "...", ...})
    """
    response = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    response.raise_for_status()
    return response.json()["email"]


def revoke_token(token: str) -> None:
    """
    Revokes an access or refresh token on Google's side (used when a staff
    member disconnects their calendar). Best-effort — response isn't checked.
    POST https://oauth2.googleapis.com/revoke

    Input:
        token="ya29.a0Af..." (an access token or a refresh token)

    Request form body: {"token": "ya29.a0Af..."}

    Output:
        None
    """
    requests.post(REVOKE_URL, data={"token": token})
