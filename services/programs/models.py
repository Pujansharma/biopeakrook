from django.db import models

from core.utils.models import BaseUUIDModel
from services.programs.utils.constants import ProgramType


class Program(BaseUUIDModel):
    customer_profile = models.ForeignKey(
        "customers.CustomerProfile", related_name="programs", on_delete=models.PROTECT
    )
    center = models.ForeignKey(
        "centers.Center", related_name="programs", on_delete=models.PROTECT
    )
    program_type = models.CharField(choices=ProgramType)
    notes = models.TextField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    is_complimentary = models.BooleanField(default=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    redeemable_centers = models.ManyToManyField(
        "centers.Center", related_name="redeemable_programs", blank=True
    )
    services_count = models.PositiveBigIntegerField(default=0, editable=False)
    sessions_count = models.PositiveBigIntegerField(default=0, editable=False)
    sessions_used = models.PositiveBigIntegerField(default=0, editable=False)
    redeemable_centers_count = models.PositiveBigIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_programs",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class ProgramService(BaseUUIDModel):
    program = models.ForeignKey(
        Program, related_name="program_services", on_delete=models.CASCADE
    )
    service = models.ForeignKey(
        "services.Service", related_name="program_services", on_delete=models.PROTECT
    )
    sessions_count = models.PositiveIntegerField(default=0)
    sessions_used = models.PositiveIntegerField(default=0, editable=False)
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_program_services",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "service"], name="unique_program_service"
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class WellnessProgram(BaseUUIDModel):
    program = models.OneToOneField(
        Program, on_delete=models.CASCADE, related_name="wellness_program"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pk}"


class RedemptionHistory(BaseUUIDModel):
    program_service = models.ForeignKey(
        ProgramService, on_delete=models.PROTECT, related_name="redemptions"
    )
    redeem_center = models.ForeignKey(
        "centers.Center", on_delete=models.PROTECT, related_name="redemptions"
    )
    redeemed_at = models.DateTimeField()
    quantity = models.PositiveIntegerField(default=0)
    redeemed_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="redeemed_histories",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Redemption Histories"

    def __str__(self):
        return f"{self.pk}"
