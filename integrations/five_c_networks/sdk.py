import io

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
    logger.info("EVO 360 access-token request started")
    response = requests.post(url, json=payload)
    if not response.ok:
        error_message = "Unable to authenticate with EVO 360"
        logger.error(
            f"EVO 360 access-token request failed: "
            f"status={response.status_code} response={response.text}"
        )
        return None, error_message
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        error_message = "EVO 360 did not provide an access token"
        logger.error(
            f"EVO 360 access-token response was empty: "
            f"status={response.status_code}"
        )
        return None, error_message
    logger.info("EVO 360 access-token request completed")
    return access_token, None


def get_access_token(client_id, client_secret):
    cache_key = f"EVO_{client_id}_{client_secret}"
    access_token = cache.get(cache_key)
    if access_token:
        logger.info("EVO 360 access token retrieved from cache")
        return access_token, None

    access_token, error = _get_credentials(
        client_id=client_id,
        client_secret=client_secret,
    )
    if error:
        return None, error

    cache.set(cache_key, access_token, 600)
    return access_token, None


def get_pdf_status(access_token, email, center_id):
    session = Session(access_token)
    url = BASE_URL + "user/pdf-status"
    payload = {
        "email": email,
        "center_id": center_id,
    }
    logger.info(
        f"EVO 360 PDF-status request started: center_id={center_id}"
    )
    response = session.post(
        url, json=payload,
    )
    if not response.ok:
        error_message = "Unable to retrieve the EVO 360 report status"
        logger.error(
            f"EVO 360 PDF-status request failed: center_id={center_id} "
            f"status={response.status_code} response={response.text}"
        )
        return None, error_message

    data = response.json()
    if not data:
        error_message = "EVO 360 returned an empty report status"
        logger.warning(
            f"EVO 360 PDF-status response was empty: center_id={center_id}"
        )
        return None, error_message

    logger.info(
        f"EVO 360 PDF-status request completed: center_id={center_id}"
    )
    return data, None


def get_pdf_report(pdf_url):
    logger.info("EVO 360 PDF download started")
    response = requests.get(pdf_url)
    if not response.ok:
        error_message = "Unable to download the EVO 360 report"
        logger.error(
            f"EVO 360 PDF download failed: status={response.status_code}"
        )
        return None, error_message

    if not response.content:
        error_message = "EVO 360 returned an empty PDF report"
        logger.warning("EVO 360 PDF download returned empty content")
        return None, error_message

    logger.info("EVO 360 PDF download completed")
    return io.BytesIO(response.content), None
