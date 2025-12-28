from core.settings.base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

INTERNAL_IPS = ['127.0.0.1']

# Database
# https://docs.djangoproject.com/en/dev/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DEV_DB_NAME'),
        'USER': config('DEV_DB_USER'),
        'PASSWORD': config('DEV_DB_PASSWORD'),
        'HOST': config('DEV_DB_HOST'),
        'PORT': config('DEV_DB_PORT'),
        'OPTIONS': {
            'sslmode': 'prefer',
        }
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

EMAIL_HOST = config('DEV_EMAIL_HOST', "")
EMAIL_PORT = config('DEV_EMAIL_PORT', "")
EMAIL_HOST_USER = config('DEV_EMAIL_HOST_USER', "")
EMAIL_HOST_PASSWORD = config('DEV_EMAIL_HOST_PASSWORD', "")
DEFAULT_FROM_EMAIL = config('DEV_DEFAULT_FROM_EMAIL', 'Local <mail@localhost>')

# Django CORS Headers

CORS_ALLOW_ALL_ORIGINS = True

# Other

PASSWORD_RESET_URL = config('DEV_PASSWORD_RESET_URL', "")
