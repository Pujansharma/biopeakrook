import requests
from django.conf import settings
from requests import RequestException

from core.utils.log import logger

GRAPH_BASE_URL = "https://graph.facebook.com"
WHATSAPP_HTTP_TIMEOUT = (5, 15)


def is_whatsapp_configured():
    return bool(
        getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
        and getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
    )


def _api_version():
    return getattr(settings, "WHATSAPP_API_VERSION", None) or "v23.0"


def _messages_url():
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    return (
        f"{GRAPH_BASE_URL}/{_api_version()}/{phone_number_id}/messages"
    )


class WhatsAppSession(requests.Session):
    def __init__(self):
        super().__init__()
        token = getattr(settings, "WHATSAPP_ACCESS_TOKEN", None) or ""
        self.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )


def _normalize_body_parameters(body_parameters):
    """
    Accept:
    - list[{"parameter_name", "text"}] (named Meta templates)
    - list[str] (legacy positional {{1}}, {{2}}, ...)
    - dict[str, str] (named shorthand)
    """
    if not body_parameters:
        return []
    if isinstance(body_parameters, dict):
        return [
            {
                "type": "text",
                "parameter_name": str(name),
                "text": str(text),
            }
            for name, text in body_parameters.items()
        ]

    parameters = []
    for entry in body_parameters:
        if isinstance(entry, dict):
            parameter_name = entry.get("parameter_name")
            text = entry.get("text", "")
            item = {"type": "text", "text": str(text)}
            if parameter_name:
                item["parameter_name"] = str(parameter_name)
            parameters.append(item)
            continue
        parameters.append({"type": "text", "text": str(entry)})
    return parameters


def send_template(
    *,
    to_phone,
    template_name,
    language_code,
    body_parameters,
):
    """
    Send an approved WhatsApp template message.

    Returns (http_status, body_dict).
    Prefer named body_parameters for Meta named-variable templates.
    """
    if not is_whatsapp_configured():
        raise ValueError("WhatsApp Cloud API is not configured")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    normalized = _normalize_body_parameters(body_parameters)
    if normalized:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": normalized,
            }
        ]

    session = WhatsAppSession()
    try:
        response = session.post(
            _messages_url(),
            json=payload,
            timeout=WHATSAPP_HTTP_TIMEOUT,
        )
    except RequestException as exc:
        logger.warning(f"WhatsApp send_template request failed: {exc}")
        return 599, {"error": {"code": "request_failed", "message": str(exc)}}
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if not response.ok:
        error = {}
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            error = body["error"]
        logger.warning(
            f"WhatsApp send_template error {response.status_code}: "
            f"code={error.get('code')} message={error.get('message')}"
        )
    return response.status_code, body


def extract_wamid(response_body):
    if not isinstance(response_body, dict):
        return ""
    messages = response_body.get("messages") or []
    if not messages:
        return ""
    return messages[0].get("id") or ""
