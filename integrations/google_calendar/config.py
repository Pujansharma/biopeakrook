from django.conf import settings

GOOGLE_CLIENT_ID = getattr(settings, "GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = getattr(settings, "GOOGLE_CLIENT_SECRET", None)
GOOGLE_REDIRECT_URI = getattr(settings, "GOOGLE_REDIRECT_URI", None)
GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY = getattr(settings, "GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY", None)
ADMIN_FRONTEND_URL = getattr(settings, "ADMIN_FRONTEND_URL", None)
