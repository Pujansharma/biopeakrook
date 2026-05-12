from django.db import models
from django.utils.translation import gettext_lazy as _

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
