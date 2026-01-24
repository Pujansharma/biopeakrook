from django.db import models

from core.utils.models import BaseUUIDModel


# Create your models here.
class Package(BaseUUIDModel):
    """Wellness packages, diagnostic bundles"""
    name = models.CharField(max_length=200)
    # Example: "Comprehensive Metabolic Health Package"

    description = models.TextField(null=True, blank=True)
    validity_days = models.PositiveIntegerField(
        null=True, blank=True
    )  # Package valid for X days

    # Pricing
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class PackageService(BaseUUIDModel):
    """Services included in a package"""
    package = models.ForeignKey(
        Package, on_delete=models.CASCADE, related_name='services'
    )
    service = models.ForeignKey(
        'services.Service', on_delete=models.CASCADE, related_name='packages'
    )

    quantity = models.PositiveIntegerField(default=1)  # Number of sessions
    sequence = models.PositiveIntegerField(default=0)  # Order of delivery

    is_mandatory = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['package', 'service'], name='uniq_service_package')
        ]

    def __str__(self):
        return f"{self.pk}"


class PackageAvailability(BaseUUIDModel):
    """Which packages are offered at which centers"""
    package = models.ForeignKey(
        Package, on_delete=models.CASCADE, related_name='center_availability'
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.CASCADE, related_name='package_availability'
    )

    # Center-specific pricing (can override package.total_price)
    pricing = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="Override package price for this center (if null, uses package price)"
    )

    # Center-specific discount (can override package.discount_percentage)
    discount_percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        help_text="Override discount for this center"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['package', 'center'],
                name='uniq_package_center'
            )
        ]
        verbose_name_plural = "Package Availability"

    def __str__(self):
        return f"{self.pk}"
