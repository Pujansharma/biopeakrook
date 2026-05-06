import secrets
import string

_COUPON_ALPHABET = string.ascii_uppercase + string.digits


def generate_redeemable_code() -> str:
    return "".join(secrets.choice(_COUPON_ALPHABET) for _ in range(10))
