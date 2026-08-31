from corsheaders.defaults import default_headers

from core.settings.base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Debug toolbar
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: True,
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
CORS_ALLOW_HEADERS = [*default_headers, "x-center-id"]

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
ADMIN_FRONTEND_URL = config("DEV_ADMIN_FRONTEND_URL", None)
