from core.settings.base import *

DEBUG = False

ALLOWED_HOSTS = ["*"]

# Database
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("STG_DB_NAME"),
        "USER": config("STG_DB_USER"),
        "PASSWORD": config("STG_DB_PASSWORD"),
        "HOST": config("STG_DB_HOST"),
        "PORT": config("STG_DB_PORT"),
        "OPTIONS": {
            "sslmode": "prefer",
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

EMAIL_USE_TLS = True
EMAIL_HOST = config("STG_EMAIL_HOST")
EMAIL_HOST_USER = config("STG_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = config("STG_EMAIL_HOST_PASSWORD")
EMAIL_PORT = config("STG_EMAIL_PORT")
DEFAULT_FROM_EMAIL = config("STG_DEFAULT_FROM_EMAIL")

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

CORS_ALLOW_ALL_ORIGINS = True

# Other

PASSWORD_BASE_URL = config("STG_PASSWORD_BASE_URL", "")

# Firebase
ADMIN_CERT = config("ADMIN_CERT", None)
APP_CERT = config("APP_CERT", None)

# Metsights
METSIGHTS_API_KEY = config('STG_METSIGHTS_API_KEY', None)

# Orange Labs
ORANGE_LABS_API_BASE_URL = config("STG_ORANGE_LABS_API_BASE_URL", None)
ORANGE_LABS_API_KEY = config("STG_ORANGE_LABS_API_KEY", None)
ORANGE_LABS_WEBHOOK_SECRET = config("STG_ORANGE_LABS_WEBHOOK_SECRET", None)

# WhatsApp Cloud API (communications)
WHATSAPP_ACCESS_TOKEN = config("STG_WHATSAPP_ACCESS_TOKEN", None)
WHATSAPP_PHONE_NUMBER_ID = config("STG_WHATSAPP_PHONE_NUMBER_ID", None)
WHATSAPP_APP_SECRET = config("STG_WHATSAPP_APP_SECRET", None)
WHATSAPP_WEBHOOK_VERIFY_TOKEN = config("STG_WHATSAPP_WEBHOOK_VERIFY_TOKEN", None)
WHATSAPP_API_VERSION = config("STG_WHATSAPP_API_VERSION", "v23.0")
WHATSAPP_WABA_ID = config("STG_WHATSAPP_WABA_ID", None)
WHATSAPP_APP_ID = config("STG_WHATSAPP_APP_ID", None)
WHATSAPP_TEMPLATE_LANGUAGE = config("STG_WHATSAPP_TEMPLATE_LANGUAGE", "en")
WHATSAPP_TEMPLATE_CONFIRMED = config(
    "STG_WHATSAPP_TEMPLATE_CONFIRMED", "appointment_confirmed"
)
WHATSAPP_TEMPLATE_CANCELLED = config(
    "STG_WHATSAPP_TEMPLATE_CANCELLED", "appointment_cancelled"
)
WHATSAPP_TEMPLATE_RESCHEDULED = config(
    "STG_WHATSAPP_TEMPLATE_RESCHEDULED", "appointment_rescheduled"
)
