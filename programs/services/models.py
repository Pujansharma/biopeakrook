from django.db import models

from core.utils.models import BaseUUIDModel
from products.models import Product
from programs.services.utils.constants import ServiceCategory


class Service(BaseUUIDModel):
    name = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_services",
    )
    service_category = models.CharField(choices=ServiceCategory)
    image = models.FileField(upload_to="products/services/", null=True, blank=True)
    is_global = models.BooleanField(default=False)
    centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    products_count = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class CenterServiceAssignment(BaseUUIDModel):
    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="center_assignments"
    )
    center = models.ForeignKey(
        "centers.Center", on_delete=models.CASCADE, related_name="service_assignments"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "center"], name="unique_service_center"
            )
        ]
        indexes = [
            models.Index(fields=["service", "center"], name="service_center_idx")
        ]

    def __str__(self):
        return f"{self.pk}"


class ServiceProductAssignment(BaseUUIDModel):
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="product_assignments"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="service_assignments"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "product"], name="unique_service_product"
            )
        ]

    def __str__(self):
        return f"{self.pk}"
