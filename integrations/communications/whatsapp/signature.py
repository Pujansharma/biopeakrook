import hashlib
import hmac


def verify_whatsapp_webhook_signature(*, body, signature_header, app_secret):
    if not app_secret or not signature_header:
        return False
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    provided_signature = signature_header[len(prefix) :]
    expected_signature = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, provided_signature)
