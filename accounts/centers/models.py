from django.db import models

from accounts.centers.utils.constants import CenterStatus
from accounts.utils import get_user_model
from appointments.utils.constants import ScheduleModes, AppointmentDays
from core.utils.models import BaseUUIDModel

User = get_user_model()


class Center(BaseUUIDModel):
    code = models.CharField(max_length=25, db_index=True, editable=False)
    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to='centers/', null=True, blank=True)

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
    modes = models.CharField(
        choices=ScheduleModes.CHOICES, default=ScheduleModes.IN_PERSON
    )
    status = models.CharField(
        choices=CenterStatus.CHOICES,
        default=CenterStatus.SETUP  # New centers start as 'setup'
    )

    # Audit
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_centers'
    )

    class Meta:
        ordering = ['-code', '-created_at']

    def __str__(self):
        return f"{self.pk}"


class CenterOperatingHour(BaseUUIDModel):
    """Global operating hours for the center"""
    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name='operating_hours'
    )

    day_of_week = models.CharField(choices=AppointmentDays.CHOICES)

    is_open = models.BooleanField(default=True)  # False for days center is closed

    open_time = models.TimeField(
        null=True, blank=True,
        help_text="Center opens at this time"
    )
    close_time = models.TimeField(
        null=True, blank=True,
        help_text="Center closes at this time"
    )

    class Meta:
        ordering = ['-created_at', 'day_of_week']
        verbose_name_plural = "Center Operating Hours"
        constraints = [
            models.UniqueConstraint(
                fields=['center', 'day_of_week', 'is_open'], name='uniq_center_closed_day',
                condition=models.Q(is_open=False)
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class CenterHoliday(BaseUUIDModel):
    center = models.ForeignKey(
        Center, on_delete=models.CASCADE, related_name='holidays'
    )
    date = models.DateField()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['center', 'date'], name='uniq_center_holiday')
        ]
