from django.db import models

from accounts.utils import get_user_model
from core.utils.models import BaseUUIDModel
from services.models import Service

User = get_user_model()


class Composite(BaseUUIDModel):
    """Wellness composites, diagnostic bundles"""
    center = models.ForeignKey(
        'centers.Center', on_delete=models.PROTECT, related_name='composites'
    )
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)

    # Computed from composite services, filled via helper functions
    calculated_pricing = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, editable=False,
    )
    calculated_duration = models.PositiveIntegerField(default=0, editable=False)

    # Effective values — defaults to calculated, can be overridden manually
    effective_pricing = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, editable=False,
    )
    effective_duration = models.PositiveIntegerField(default=0, editable=False)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_composites'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class CompositeService(BaseUUIDModel):
    """Services included in a package"""
    composite = models.ForeignKey(
        Composite, on_delete=models.CASCADE, related_name='composite_services'
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name='composite_services'
    )

    quantity = models.PositiveIntegerField(default=1)  # Number of sessions
    sequence = models.PositiveIntegerField(default=0)  # Order of delivery

    is_mandatory = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_composite_services'
    )

    class Meta:
        ordering = ['sequence', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['composite', 'service'], name='uniq_composite_service'
            )
        ]

    def __str__(self):
        return f"{self.pk}"
