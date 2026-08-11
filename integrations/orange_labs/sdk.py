import requests
from django.conf import settings
from urllib.parse import urlencode

from core.utils.log import logger

ORANGE_LABS_API_BASE_URL = getattr(settings, "ORANGE_LABS_API_BASE_URL", None)
ORANGE_LABS_API_KEY = getattr(settings, "ORANGE_LABS_API_KEY", None)


class OrangeLabsSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.headers.update(
            {
                "api_key": ORANGE_LABS_API_KEY or "",
                "Content-Type": "application/json",
            }
        )


def _require_base_url():
    if not ORANGE_LABS_API_BASE_URL:
        raise ValueError("ORANGE_LABS_API_BASE_URL is not configured")
    return ORANGE_LABS_API_BASE_URL.rstrip("/")


def check_serviceability(address, request_date):
    base_url = _require_base_url()
    url_encoded_params = urlencode({"address": address, "request_date": request_date})
    url = f"{base_url}/v1/partner/serviceability?{url_encoded_params}"
    print(f"url: {url}")
    session = OrangeLabsSession()
    response = session.get(url)
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    if not response.ok and response.status_code != 400:
        logger.warning(
            f"Orange Labs serviceability error {response.status_code}: {payload}"
        )
    return response.status_code, payload


def create_order(payload):
    base_url = _require_base_url()
    url = f"{base_url}/v1/partner/order"
    session = OrangeLabsSession()
    response = session.post(url, json=payload)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if not response.ok:
        logger.warning(f"Orange Labs create order error {response.status_code}: {body}")
    return response.status_code, body


def reschedule_order(request_id, token, requested_slot_time, reason, explanation):
    base_url = _require_base_url()
    url = f"{base_url}/v1/partner/{request_id}/reschedule"
    session = OrangeLabsSession()
    response = session.patch(
        url,
        params={"token": token},
        json={
            "requested_slot_time": requested_slot_time,
            "reschedule_reason": reason,
            "reschedule_explanation": explanation,
        },
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if not response.ok:
        logger.warning(f"Orange Labs reschedule error {response.status_code}: {body}")
    return response.status_code, body


def cancel_order(request_id, token, reason, explanation):
    base_url = _require_base_url()
    url = f"{base_url}/v1/partner/{request_id}/cancel"
    session = OrangeLabsSession()
    response = session.patch(
        url,
        params={"token": token},
        json={
            "cancellationReason": reason,
            "cancellationExplanation": explanation,
        },
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if not response.ok:
        logger.warning(f"Orange Labs cancel error {response.status_code}: {body}")
    return response.status_code, body
