from django import forms
from django.conf import settings
from django.db.models import CharField
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from core.utils.formatters import PhoneNumberFormat
from core.utils.validators import PhoneNumberValidator

PHONE_NUMBER_MAX_LENGTH = getattr(settings, "PHONE_NUMBER_MAX_LENGTH", 20)


class PhoneNumberField(CharField):
    default_validators = []

    def __init__(self, region="IN", **kwargs):
        self.region = region
        kwargs.setdefault("max_length", PHONE_NUMBER_MAX_LENGTH)
        super().__init__(**kwargs)
        self.validators.append(PhoneNumberValidator(region=region))
        self.error_messages = {
            "unique": _("A user with that phone number already exists."),
        }
        self.help_text = _("Phone number with country code.")

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return value

        phone_formatter = PhoneNumberFormat(value, region=self.region)
        cleaned_value = phone_formatter.clean(raise_exception=False)
        return cleaned_value if cleaned_value else value


class PhoneNumberFormField(forms.CharField):
    default_validators = []

    def __init__(self, region="IN", **kwargs):
        self.region = region
        kwargs.setdefault("max_length", PHONE_NUMBER_MAX_LENGTH)
        super().__init__(**kwargs)
        self.validators.append(PhoneNumberValidator(region=region))

    def to_python(self, value):
        value = super().to_python(value)
        if value in self.empty_values:
            return value

        phone_formatter = PhoneNumberFormat(value, region=self.region)
        cleaned_value = phone_formatter.clean(raise_exception=False)
        return cleaned_value if cleaned_value else value


class PhoneNumberSerializerField(serializers.CharField):
    def __init__(self, region="IN", **kwargs):
        self.region = region
        kwargs.setdefault("max_length", PHONE_NUMBER_MAX_LENGTH)
        super().__init__(**kwargs)
        self.validators.append(PhoneNumberValidator(region=region))
        self.error_messages.update(
            {
                "unique": _("A user with that phone number already exists."),
            }
        )
        self.help_text = _("Phone number with country code.")

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        if not data:
            return None

        phone_formatter = PhoneNumberFormat(data, region=self.region)
        cleaned_value = phone_formatter.clean(raise_exception=False)
        return cleaned_value if cleaned_value else data
