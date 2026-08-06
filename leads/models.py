from django.contrib.postgres.fields import ArrayField
from django.db import models

from accounts.centers.models import Center
from accounts.customers.models import CustomerProfile
from accounts.users.models import Gender
from accounts.utils.auth import get_user_model
from core.utils.fields import PhoneNumberField
from core.utils.models import BaseUUIDModel
from leads.utils.constants import LeadPackages

User = get_user_model()


class Lead(BaseUUIDModel):
    unique_id = models.CharField(max_length=25, db_index=True, editable=False)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(
        max_length=1, choices=Gender.CHOICES, null=True, blank=True
    )
    phone = PhoneNumberField(unique=True)
    email = models.EmailField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_client = models.BooleanField(default=False)
    is_request_sent = models.BooleanField(default=False)
    is_onboarding_sent = models.BooleanField(default=False)
    converted_on = models.DateTimeField(null=True, blank=True)
    home_center = models.ForeignKey(
        Center, on_delete=models.SET_NULL, null=True, blank=True
    )
    is_invited = models.BooleanField(default=False)
    is_joined = models.BooleanField(default=False)

    packages = ArrayField(
        models.CharField(max_length=4, choices=LeadPackages),
        null=True,
        blank=True,
        default=list,
    )

    customer_profile = models.OneToOneField(
        CustomerProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lead",
    )
    created_by = models.ForeignKey(
        User,
        related_name="created_leads",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        User,
        related_name="updated_leads",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    data = models.JSONField(editable=False, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pk}"


class LeadSummary(BaseUUIDModel):
    key = models.CharField(
        max_length=25,
        default="GLOBAL",
        unique=True,
        editable=False,
    )
    leads_total = models.PositiveBigIntegerField(default=0, editable=False)
    leads_converted = models.PositiveBigIntegerField(default=0, editable=False)
    leads_assigned = models.PositiveBigIntegerField(default=0, editable=False)
    leads_inactive = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        verbose_name_plural = "Lead summaries"

    def __str__(self) -> str:
        return f"{self.pk}"
