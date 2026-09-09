from django.db import models

from accounts.centers.utils.constants import CenterStatus, CenterClosureType
from accounts.utils import get_user_model
from core.utils.constants import AppointmentDays, AppointmentModes
from core.utils.models import BaseUUIDModel

User = get_user_model()


class Center(BaseUUIDModel):
    code = models.CharField(max_length=25, db_index=True, editable=False)
    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to="centers/", null=True, blank=True)

    # Address information
    address = models.CharField(null=True)
    address_line_1 = models.CharField(null=True)
    address_line_2 = models.CharField(null=True)

    city = models.CharField(max_length=50, null=True, blank=True)
    state = models.CharField(max_length=50, null=True, blank=True)
    country = models.CharField(max_length=20, null=True, blank=True)
    pincode = models.CharField(max_length=20, null=True, blank=True)

    # Contact Information
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    contact_person = models.CharField(max_length=100, blank=True)

    # Operating Configuration
    modes = models.CharField(choices=AppointmentModes, default=AppointmentModes.IN_PERSON)
    status = models.CharField(
        choices=CenterStatus.CHOICES,
        default=CenterStatus.SETUP,  # New centers start as 'setup'
    )

    # Statistics
    staff_count = models.PositiveBigIntegerField(default=0, editable=False)
    inactive_staff_count = models.PositiveBigIntegerField(default=0, editable=False)
    customer_count = models.PositiveBigIntegerField(default=0, editable=False)
    inactive_customer_count = models.PositiveBigIntegerField(default=0, editable=False)

    # Audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_centers",
    )

    class Meta:
        ordering = ["-code", "-created_at"]

    def __str__(self):
        return f"{self.pk}"

    @property
    def full_address(self) -> str:
        region = " ".join(part for part in (self.state, self.pincode) if part)
        address_parts = [
            self.name,
            self.address_line_1,
            self.address_line_2,
            self.city,
            region,
        ]
        return ", ".join(part for part in address_parts if part)


class CenterOperatingHour(BaseUUIDModel):
    """Global operating hours for the center"""

    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="operating_hours"
    )

    day_of_week = models.CharField(choices=AppointmentDays)

    is_open = models.BooleanField(default=True)  # False for days center is closed

    open_time = models.TimeField(
        null=True, blank=True, help_text="Center opens at this time"
    )
    close_time = models.TimeField(
        null=True, blank=True, help_text="Center closes at this time"
    )

    class Meta:
        ordering = ["-created_at", "day_of_week"]
        verbose_name_plural = "Center Operating Hours"
        constraints = [
            models.UniqueConstraint(
                fields=["center", "day_of_week", "is_open"],
                name="uniq_center_closed_day",
                condition=models.Q(is_open=False),
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class CenterClosure(BaseUUIDModel):
    """Full-day center closure (holiday or manual closed day)."""

    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name="closures"
    )
    date = models.DateField()
    type = models.CharField(
        choices=CenterClosureType,
        default=CenterClosureType.MANUAL,
    )
    reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["center", "date"], name="uniq_center_closure"
            )
        ]

    def __str__(self):
        return f"{self.pk}"
