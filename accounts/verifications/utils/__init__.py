import base64
import random
import secrets
from datetime import timedelta
from io import BytesIO

import pyotp
import qrcode
from django.utils import timezone


def generate_expiry():
    return timezone.now() + timedelta(days=7)


def generate_secret_code():
    return secrets.token_hex(32)


def get_expiry(minutes=2):
    return timezone.now() + timedelta(minutes=minutes)


def get_totp_expiry():
    return get_expiry(5)


def get_counter():
    return random.randint(1, 32767)


def get_secret():
    secret = pyotp.random_base32()
    return secret


def get_code(secret, counter):
    h_otp = pyotp.HOTP(secret)
    code = h_otp.at(counter)
    return code


def code_valid(secret, counter, code):
    if not secret:
        return None
    h_otp = pyotp.HOTP(secret)
    return h_otp.verify(code, counter)


def get_two_factor_uri(secret, name):
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=name, issuer_name="Biopeak")
    return uri


def get_qr_code_data_uri(data):
    buffer = BytesIO()
    qrcode.make(data).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def verify_two_factor_code(secret, code):
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
