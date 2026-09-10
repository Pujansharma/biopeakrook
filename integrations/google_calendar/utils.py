from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from cryptography.fernet import Fernet

GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY = getattr(settings, "GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY", None)

_fernet_instance = None


def _get_fernet():
    global _fernet_instance
    if _fernet_instance is None:
        if not GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY:
            raise ImproperlyConfigured(
                "GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY is not set."
            )
        _fernet_instance = Fernet(GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY.encode())
    return _fernet_instance


def ensure_encryption_configured():
    _get_fernet()

def encrypt(plaintext: str):
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str):
    return _get_fernet().decrypt(ciphertext.encode()).decode()
