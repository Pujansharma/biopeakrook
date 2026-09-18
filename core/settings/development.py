from corsheaders.defaults import default_headers

from core.settings.base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Debug toolbar
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: True,
    "IS_RUNNING_TESTS": False,
}

# Database
# https://docs.djangoproject.com/en/dev/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DEV_DB_NAME"),
        "USER": config("DEV_DB_USER"),
        "PASSWORD": config("DEV_DB_PASSWORD"),
        "HOST": config("DEV_DB_HOST"),
        "PORT": config("DEV_DB_PORT"),
        "OPTIONS": {
            "sslmode": "prefer",
        },
    }
}

# Storages
# https://docs.djangoproject.com/en/dev/ref/settings/#storages

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Email
# https://docs.djangoproject.com/en/dev/ref/settings/#email
DEFAULT_FROM_EMAIL = config("DEV_DEFAULT_FROM_EMAIL", "Local <mail@localhost>")

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": config("DEV_EMAIL_HOST", ""),
            "use_tls": False,
            "port": config("DEV_EMAIL_PORT", ""),
            "username": config("DEV_EMAIL_HOST_USER", ""),
            "password": config("DEV_EMAIL_HOST_PASSWORD", ""),
        },
    },
}
# Django CORS Headers

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = [*default_headers, "x-center-id", "idempotency-key"]

PASSWORD_BASE_URL = config("DEV_PASSWORD_BASE_URL", "")

# Firebase
ADMIN_CERT = config("ADMIN_CERT", None)
APP_CERT = config("APP_CERT", None)

# Metsights
METSIGHTS_BASE_URL = config('DEV_METSIGHTS_BASE_URL', None)
METSIGHTS_API_KEY = config('DEV_METSIGHTS_API_KEY', None)

# Orange Labs
ORANGE_LABS_API_BASE_URL = config("DEV_ORANGE_LABS_API_BASE_URL", None)
ORANGE_LABS_API_KEY = config("DEV_ORANGE_LABS_API_KEY", None)
ORANGE_LABS_WEBHOOK_SECRET = config("DEV_ORANGE_LABS_WEBHOOK_SECRET", None)

# Google Calendar
GOOGLE_CLIENT_ID = config("DEV_GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = config("DEV_GOOGLE_CLIENT_SECRET", None)
GOOGLE_REDIRECT_URI = config("DEV_GOOGLE_REDIRECT_URI", None)
GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY = config("DEV_GOOGLE_CALENDAR_TOKEN_ENCRYPTION_KEY", None)
GOOGLE_CALENDAR_ID = config("DEV_GOOGLE_CALENDAR_ID", None)
BE_SERVICE_BASE_URL = config("DEV_BE_SERVICE_BASE_URL", None)
ADMIN_FRONTEND_URL = config("DEV_ADMIN_FRONTEND_URL", None)
COMMUNICATION_OUTBOX_WAKE_QUEUE_URL = config(
    "DEV_COMMUNICATION_OUTBOX_WAKE_QUEUE_URL", default=""
)
AWS_REGION = config("AWS_REGION", default=None)
# WhatsApp Cloud API (communications)
WHATSAPP_ACCESS_TOKEN = config("DEV_WHATSAPP_ACCESS_TOKEN", None)
WHATSAPP_PHONE_NUMBER_ID = config("DEV_WHATSAPP_PHONE_NUMBER_ID", None)
WHATSAPP_APP_SECRET = config("DEV_WHATSAPP_APP_SECRET", None)
WHATSAPP_WEBHOOK_VERIFY_TOKEN = config("DEV_WHATSAPP_WEBHOOK_VERIFY_TOKEN", None)
WHATSAPP_API_VERSION = config("DEV_WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_WABA_ID = config("DEV_WHATSAPP_WABA_ID", None)
WHATSAPP_APP_ID = config("DEV_WHATSAPP_APP_ID", None)
WHATSAPP_TEMPLATE_LANGUAGE = config("DEV_WHATSAPP_TEMPLATE_LANGUAGE", "en")
WHATSAPP_TEMPLATE_CONFIRMED = config(
    "DEV_WHATSAPP_TEMPLATE_CONFIRMED", "appointment_confirmed"
)
WHATSAPP_TEMPLATE_CANCELLED = config(
    "DEV_WHATSAPP_TEMPLATE_CANCELLED", "appointment_cancelled"
)
WHATSAPP_TEMPLATE_RESCHEDULED = config(
    "DEV_WHATSAPP_TEMPLATE_RESCHEDULED", "appointment_rescheduled"
)
