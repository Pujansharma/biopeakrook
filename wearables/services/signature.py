import hashlib
import hmac

from django.conf import settings


def signature_message(payload: dict) -> str:
    values = [
        payload.get(field_name)
        for field_name in ("client_uuid", "user_id", "datetime")
    ]
    if not all(isinstance(value, str) and value for value in values):
        return ""
    return "".join(values)


def verify_rook_webhook_signature(
    *,
    payload,
    signature_header: str,
) -> bool:
    hash_key = getattr(settings, "ROOK_WEBHOOK_HASH_KEY", "")
    allow_unsigned = getattr(settings, "ROOK_ALLOW_UNSIGNED_WEBHOOKS", False)
    if not hash_key:
        return allow_unsigned
    if not isinstance(payload, dict) or not signature_header:
        return False
    message = signature_message(payload)
    if not message:
        return False
    expected_signature = hmac.new(
        key=hash_key.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)

