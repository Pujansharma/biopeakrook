from corsheaders.defaults import default_headers

from core.settings.base import *

DEBUG = False

ALLOWED_HOSTS = ["*"]

# Database
# https://docs.djangoproject.com/en/dev/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("PRD_DB_NAME"),
        "USER": config("PRD_DB_USER"),
        "PASSWORD": config("PRD_DB_PASSWORD"),
        "HOST": config("PRD_DB_HOST"),
        "PORT": config("PRD_DB_PORT"),
        "OPTIONS": {
            # 'sslmode': 'required',
        },
    }
}

# Storages
# https://docs.djangoproject.com/en/dev/ref/settings/#storages

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# AWS Settings
# https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html

AWS_QUERYSTRING_AUTH = False
AWS_S3_ACCESS_KEY_ID = config("AWS_S3_ACCESS_KEY_ID")
AWS_S3_SECRET_ACCESS_KEY = config("AWS_S3_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME")
AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN")

# Email
# https://docs.djangoproject.com/en/dev/ref/settings/#email
DEFAULT_FROM_EMAIL = config("PRD_DEFAULT_FROM_EMAIL")

# https://docs.djangoproject.com/en/latest/howto/mailers-migration/#migrating-settings
MAILERS = {
    "default": {
        "BACKEND":"django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": config("PRD_EMAIL_HOST"),
            "use_tls": True,
            "username":  config("PRD_EMAIL_HOST_USER"),
            "password": config("PRD_EMAIL_HOST_PASSWORD"),
        },
    },
}

# Logging
# https://docs.djangoproject.com/en/dev/ref/settings/#logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "django.server": {
            "()": "core.utils.log.BaseFormatter",
            "format": "[{server_time}] {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "filters": [],
            "class": "logging.StreamHandler",
            "formatter": "django.server",
        },
    },
    "loggers": {
        "django": {
            "handlers": [
                "console",
            ],
            "level": "INFO",
        },
        "django.request": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Django CORS Headers

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://[\w-]+\.biopeak\.com$",
]
CORS_ALLOW_HEADERS = [*default_headers, "x-center-id", "idempotency-key"]

# Other

PASSWORD_BASE_URL = config("PRD_PASSWORD_BASE_URL", "")

# Firebase
ADMIN_CERT = config("ADMIN_CERT", None)
APP_CERT = config("APP_CERT", None)

# Metsights
METSIGHTS_API_KEY = config('PRD_METSIGHTS_API_KEY', None)

# Orange Labs
ORANGE_LABS_API_BASE_URL = config("PRD_ORANGE_LABS_API_BASE_URL", None)
ORANGE_LABS_API_KEY = config("PRD_ORANGE_LABS_API_KEY", None)
ORANGE_LABS_WEBHOOK_SECRET = config("PRD_ORANGE_LABS_WEBHOOK_SECRET", None)

# WhatsApp Cloud API (communications)
WHATSAPP_ACCESS_TOKEN = config("PRD_WHATSAPP_ACCESS_TOKEN", None)
WHATSAPP_PHONE_NUMBER_ID = config("PRD_WHATSAPP_PHONE_NUMBER_ID", None)
WHATSAPP_APP_SECRET = config("PRD_WHATSAPP_APP_SECRET", None)
WHATSAPP_WEBHOOK_VERIFY_TOKEN = config("PRD_WHATSAPP_WEBHOOK_VERIFY_TOKEN", None)
WHATSAPP_API_VERSION = config("PRD_WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_WABA_ID = config("PRD_WHATSAPP_WABA_ID", None)
WHATSAPP_APP_ID = config("PRD_WHATSAPP_APP_ID", None)
WHATSAPP_TEMPLATE_LANGUAGE = config("PRD_WHATSAPP_TEMPLATE_LANGUAGE", "en")
WHATSAPP_TEMPLATE_CONFIRMED = config(
    "PRD_WHATSAPP_TEMPLATE_CONFIRMED", "appointment_confirmed"
)
WHATSAPP_TEMPLATE_CANCELLED = config(
    "PRD_WHATSAPP_TEMPLATE_CANCELLED", "appointment_cancelled"
)
WHATSAPP_TEMPLATE_RESCHEDULED = config(
    "PRD_WHATSAPP_TEMPLATE_RESCHEDULED", "appointment_rescheduled"
)
