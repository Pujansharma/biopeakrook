from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from integrations.google_calendar.config import GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY

IST = timezone(timedelta(hours=5, minutes=30))
_fernet = Fernet(GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY)


def now_ist() -> datetime:
    """
    Input: none
    Output: datetime(2026, 9, 1, 15, 30, 0, tzinfo=IST) — current time in IST.
    """
    return datetime.now(IST)


def encrypt(plaintext: str) -> str:
    """
    Encrypts a token before it's stored in the database.

    Input:  plaintext="ya29.a0Af..." (a raw Google access/refresh token)
    Output: "gAAAAABo...==" (Fernet ciphertext, safe to store in a text column)
    """
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Reverses `encrypt()` — used right before a stored token is sent to Google.

    Input:  ciphertext="gAAAAABo...==" (value read from the database)
    Output: "ya29.a0Af..." (the original plaintext token)
    """
    return _fernet.decrypt(ciphertext.encode()).decode()
