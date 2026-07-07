from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.organizations.utils.constants import FeatureTabOptions
from core.utils.models import BaseUUIDModel


class OrganizationType(models.TextChoices):
    PLATFORM = "platform", "Platform"


class Organization(BaseUUIDModel):
    name = models.CharField(_("name"), max_length=200)
    slug = models.CharField(max_length=255, unique=True, blank=True)
    code = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(null=True, blank=True, upload_to="organizations/")
    organization_type = models.CharField(
        choices=OrganizationType,
        default=OrganizationType.PLATFORM,
        unique=True,
        editable=False,
    )

    # Count statistics
    centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    inactive_centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    staff_count = models.PositiveBigIntegerField(default=0, editable=False)
    inactive_staff_count = models.PositiveBigIntegerField(default=0, editable=False)
    customer_count = models.PositiveBigIntegerField(default=0, editable=False)
    inactive_customer_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class PlatformFeature(BaseUUIDModel):
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name="feature"
    )

    is_copilot_chat_enabled = models.BooleanField(
        default=False,
        help_text=_("Enables the Copilot Chat feature for this organization."),
    )
    is_stable = models.BooleanField(
        default=False, help_text=_("Indicates if the app is stable or not")
    )
    enabled_tabs = ArrayField(
        base_field=models.CharField(choices=FeatureTabOptions),
        default=list,
        blank=True,
        help_text=_("List of tabs visible to profiles in this organization."),
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
