from django.db import models

from core.utils.models import BaseUUIDModel


# Create your models here.
class StrandGenomicsWebhook(BaseUUIDModel):
    data = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
