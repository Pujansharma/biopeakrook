from django.conf import settings
from cryptography.fernet import Fernet

GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY = getattr(settings, "GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY", None)

_fernet_instance = None


def _get_fernet():
    """
    Input: none
    Output: a `cryptography.fernet.Fernet` instance built from
        `GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY` (cached after the first call).
    """
    global _fernet_instance
    if _fernet_instance is None:
        _fernet_instance = Fernet(GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY.encode())
    return _fernet_instance


def encrypt(plaintext: str):
    """
    Encrypts a token before it's stored in the database.

    Input:  plaintext="ya29.a0Af..." (a raw Google access/refresh token)
    Output: "gAAAAABo...==" (Fernet ciphertext, safe to store in a text column)
    """
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str):
    """
    Reverses `encrypt()` - used right before a stored token is sent to Google.

    Input:  ciphertext="gAAAAABo...==" (value read from the database)
    Output: "ya29.a0Af..." (the original plaintext token)
    """
    return _get_fernet().decrypt(ciphertext.encode()).decode()
