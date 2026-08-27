import requests
from django.core.cache import cache

from core.utils.log import logger

BASE_URL = "https://api-evo.5cnetwork.com/api/v1/"


class Session(requests.Session):
    def __init__(self, access_token):
        super().__init__()
        self.headers.update({
            "Authorization": "Bearer " + access_token,
            "User-Agent": "Biopeak-Nexus/1.0",
        })


def _get_credentials(client_id, client_secret):
    url = BASE_URL + "auth/external/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(url, json=payload)
    if not response.ok:
        logger.error(f"Error response from EVO credentials endpoint: {response.text}")
        return None
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        logger.error("No access token received from EVO credentials endpoint")
        return None
    return access_token


def get_access_token(client_id, client_secret):
    cache_key = f"EVO_{client_id}_{client_secret}"
    access_token = cache.get(cache_key)
    if not access_token:
        access_token = _get_credentials(client_id, client_secret)
        cache.set(cache_key, access_token, 600)
    return access_token


def get_pdf_status(access_token, email, center_id):
    session = Session(access_token)
    url = BASE_URL + "user/pdf-status"
    payload = {
        "email": email,
        "center_id": center_id,
    }
    response = session.post(
        url, json=payload,
    )
    if not response.ok:
        logger.error(f"Error in getting PDF status, exiting. {response.text}")
        return None

    data = response.json()
    return data
