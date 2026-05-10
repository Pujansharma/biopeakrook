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

EMAIL_USE_TLS = True
EMAIL_HOST = config("PRD_EMAIL_HOST")
EMAIL_HOST_USER = config("PRD_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = config("PRD_EMAIL_HOST_PASSWORD")
EMAIL_PORT = config("PRD_EMAIL_PORT")
DEFAULT_FROM_EMAIL = config("PRD_DEFAULT_FROM_EMAIL")

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
CORS_ALLOW_HEADERS = [*default_headers, "x-center-id"]

# Other

PASSWORD_RESET_URL = config("PRD_PASSWORD_RESET_URL", "")
