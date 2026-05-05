from django.db import models

from core.utils.models import BaseUUIDModel


class Service(BaseUUIDModel):
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_services",
    )
    centers = models.ManyToManyField(
        "centers.Center", blank=True, related_name="services"
    )
    centers_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"
