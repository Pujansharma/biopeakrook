from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

from core.utils.formatters import PhoneNumberFormat


class UsernameValidator(UnicodeUsernameValidator):
    regex = r"^[\w.+-]+\Z"
    message = _(
        "Enter a valid username. This value may contain only letters, "
        "numbers, and ./+/-/_ characters."
    )
    flags = 0


@deconstructible
class PhoneNumberValidator:
    message = _("Enter a valid phone number.")
    code = "invalid"

    def __init__(self, region="IN", message=None, code=None):
        self.region = region
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code

    def __call__(self, value):
        phone_formatter = PhoneNumberFormat(value, region=self.region)
        try:
            cleaned_value = phone_formatter.clean(raise_exception=True)
            return cleaned_value
        except Exception:
            raise ValidationError(self.message, code=self.code)
