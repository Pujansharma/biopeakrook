from django.db import models
from django.utils.text import gettext_lazy as _

from accounts.users.models import User
from core.utils.fields import PhoneNumberField
from core.utils.models import BaseModel, BaseUUIDModel
from .utils import get_expiry, generate_code, generate_expiry, get_code


class PhoneVerification(BaseUUIDModel):
    phone = PhoneNumberField(_("phone number"))
    counter = models.PositiveSmallIntegerField(default=0, editable=False)
    retry_count = models.PositiveSmallIntegerField(default=0, editable=False)
    secret = models.TextField(null=True, blank=True, editable=False)
    expires_at = models.DateTimeField(default=get_expiry)
    verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    PURPOSE_LOGIN = "0"
    PURPOSE_REGISTER = "1"
    PURPOSE_VERIFY = "2"
    PURPOSE_CHOICES = (
        (PURPOSE_LOGIN, _("Login")),
        (PURPOSE_REGISTER, _("Register")),
        (PURPOSE_VERIFY, _("Verify")),
    )
    purpose = models.CharField(
        choices=PURPOSE_CHOICES, max_length=1, default=PURPOSE_VERIFY
    )

    class Meta:
        ordering = ["-expires_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["phone", "purpose"], name="uniq_phone_purpose"
            )
        ]

    def __str__(self):
        return f"{self.pk}"

    def get_otp_code(self):
        return get_code(secret=self.secret, counter=self.counter)


class RegistrationCode(BaseModel):
    user = models.OneToOneField(
        User,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="registration_code",
    )
    code = models.CharField(
        max_length=200, default=generate_code, db_index=True, editable=False
    )
    expires_at = models.DateTimeField(default=generate_expiry)

    class Meta:
        ordering = ["-expires_at"]

    def __str__(self):
        return f"{self.pk}"


class TwoFactorCode(BaseModel):
    user = models.OneToOneField(
        User, primary_key=True, on_delete=models.CASCADE, related_name="two_factor_code"
    )
    secret = models.TextField(editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
