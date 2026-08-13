import hashlib
import hmac


def verify_orange_webhook_signature(*, body, signature_header, secret):
    if not secret or not signature_header:
        return False
    expected_signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)
