import hashlib
import hmac
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from decouple import config
from django.utils import timezone

logger = logging.getLogger(__name__)

EVENT_SESSION_COMPLETED = "preconsultation.session.completed"

_SIGNATURE_HEADER = "X-Biopeak-Signature"
_DELIVERY_HEADER = "X-Biopeak-Delivery"
_EVENT_HEADER = "X-Biopeak-Event"

_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (1.0, 4.0)
_RETRY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

_webhook_executor = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="generation-webhook"
)


def _webhook_url() -> str:
    base = config("TOOLS_URL", default="").strip()
    if not base:
        raise ValueError("TOOLS_URL is not set")
    path = config("PRECONS_TOOL_TRIGGER_API", default="").strip()
    if not path:
        raise ValueError("PRECONS_TOOL_TRIGGER_API is not set")

    # if not base.lower().startswith("https://"):
    #     raise ValueError(f"TOOLS_URL must use https, got {base!r}.")
    return base.rstrip("/") + "/" + path.lstrip("/")


def _webhook_secret() -> str:
    secret = config("ONBOARDING_WEBHOOK_SECRET", default="").strip()
    if not secret:
        raise ValueError("ONBOARDING_WEBHOOK_SECRET is not set.")
    return secret


def _sign(secret: str, timestamp: int, body: bytes) -> str:
    signed_payload = f"{timestamp}.".encode() + body
    digest = hmac.new(
        secret.encode(), signed_payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def build_session_completed_payload(session_id: str, user_id: str) -> dict:
    return {
        "event": EVENT_SESSION_COMPLETED,
        "occurred_at": timezone.now().isoformat(),
        "data": {
            "session_id": str(session_id),
            "user_id": str(user_id),
        },
    }


def _deliver(payload: dict, url: str, secret: str, delivery_id: str) -> None:
    session_id = payload["data"]["session_id"]
    try:
        body = json.dumps(payload, separators=(",", ":")).encode()
    except (TypeError, ValueError) as exc:
        logger.error(
            f"Generation webhook payload not serializable for session "
            f"{session_id}: {exc}",
            extra={"session_id": session_id, "delivery_id": delivery_id},
        )
        return

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        headers = {
            "Content-Type": "application/json",
            _SIGNATURE_HEADER: _sign(secret, int(time.time()), body),
            _DELIVERY_HEADER: delivery_id,
            _EVENT_HEADER: payload["event"],
        }
        try:
            response = requests.post(
                url,
                data=body,
                headers=headers,
                timeout=10,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            logger.warning(
                f"Generation webhook attempt {attempt}/{_MAX_ATTEMPTS} for session "
                f"{session_id} failed: {exc}",
                extra={"session_id": session_id, "delivery_id": delivery_id},
            )
        else:
            if 200 <= response.status_code < 300:
                logger.info(
                    f"Generation webhook delivered for session {session_id}: "
                    f"status={response.status_code}",
                    extra={
                        "session_id": session_id,
                        "delivery_id": delivery_id,
                    },
                )
                return
            if response.status_code not in _RETRY_STATUS_CODES:
                logger.error(
                    f"Generation webhook rejected for session {session_id}: "
                    f"status={response.status_code} (not retryable)",
                    extra={
                        "session_id": session_id,
                        "delivery_id": delivery_id,
                    },
                )
                return
            logger.warning(
                f"Generation webhook attempt {attempt}/{_MAX_ATTEMPTS} for session "
                f"{session_id} got retryable status={response.status_code}",
                extra={"session_id": session_id, "delivery_id": delivery_id},
            )

        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_SECONDS[attempt - 1])

    logger.error(
        f"Generation webhook exhausted {_MAX_ATTEMPTS} attempts for session "
        f"{session_id}; artifacts row stays PENDING for reconciliation",
        extra={"session_id": session_id, "delivery_id": delivery_id},
    )


def trigger_post_completion_generation(session_id: str, user_id: str) -> None:
    try:
        url = _webhook_url()
        secret = _webhook_secret()
    except ValueError as exc:
        logger.error(
            f"Generation webhook not fired for session {session_id}: {exc}",
            extra={"session_id": session_id},
        )
        return

    delivery_id = str(uuid.uuid4())
    payload = build_session_completed_payload(session_id, user_id)
    logger.info(
        f"Dispatching generation webhook for session {session_id}",
        extra={"session_id": session_id, "delivery_id": delivery_id},
    )
    try:
        _webhook_executor.submit(_deliver, payload, url, secret, delivery_id)
    except RuntimeError as exc:
        logger.error(
            f"Generation webhook not queued for session {session_id}: {exc}",
            extra={"session_id": session_id},
        )
