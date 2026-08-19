import secrets
import string

from sequences.utils import get_next_sequence

_COUPON_ALPHABET = string.ascii_uppercase + string.digits


def generate_redeemable_code() -> str:
    return "".join(secrets.choice(_COUPON_ALPHABET) for _ in range(10))


def generate_program_unique_id():
    name = "programs"
    sequence_value = get_next_sequence(name, fill_length=4)
    return f"PID{sequence_value}"
