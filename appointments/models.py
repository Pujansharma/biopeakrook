from datetime import time

from django.core import validators
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.utils import get_user_model
from appointments.utils.constants import (
    AppointmentStatus, AppointmentDays, ScheduleModes, AppointmentModes
)
from core.utils.models import BaseUUIDModel

User = get_user_model()


class Schedule(BaseUUIDModel):
    associate = models.ForeignKey(
        'associates.Associate', on_delete=models.CASCADE, related_name='schedules'
    )

    day_of_week = models.CharField(choices=AppointmentDays.CHOICES)

    start_time = models.TimeField(
        validators=[
            validators.MinValueValidator(time(0, 0, 0)),
            validators.MaxValueValidator(time(23, 59, 59))
        ]
    )
    end_time = models.TimeField(
        validators=[
            validators.MinValueValidator(time(0, 0, 0)),
            validators.MaxValueValidator(time(23, 59, 59))
        ]
    )
    duration = models.PositiveSmallIntegerField(
        _("Duration (in minutes)"), help_text=_("Enter duration of the slots in minutes"),
        validators=[
            validators.MinValueValidator(10),
            validators.MaxValueValidator(180)
        ]
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.RESTRICT, related_name='schedules'
    )

    mode = models.CharField(choices=ScheduleModes.CHOICES)

    buffer_time = models.PositiveSmallIntegerField(
        default=0,
        help_text="Buffer time in minutes between appointments"
    )

    valid_from = models.DateField(
        null=True, blank=True,
        help_text="Schedule becomes active from this date"
    )
    valid_until = models.DateField(
        null=True, blank=True,
        help_text="Schedule is valid until this date (e.g., Dec 12, 2025)"
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pk}"


class BlockedPeriod(BaseUUIDModel):
    associate = models.ForeignKey(
        'associates.Associate', on_delete=models.CASCADE, related_name='blocked_periods'
    )

    start_datetime = models.DateTimeField()  # UTC
    end_datetime = models.DateTimeField()  # UTC

    reason = models.CharField(
        max_length=255, blank=True,
        help_text="e.g., 'Vacation', 'Conference', 'Emergency'"
    )

    class Meta:
        ordering = ['start_datetime']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_datetime__gt=models.F('start_datetime')),
                name='blocked_period_end_after_start'
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class Appointment(BaseUUIDModel):
    associate = models.ForeignKey(
        'associates.Associate', on_delete=models.CASCADE, related_name='appointments'
    )
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.CASCADE,
        related_name='appointments'
    )
    center = models.ForeignKey(
        'centers.Center', on_delete=models.PROTECT, related_name='appointments'
    )

    mode = models.CharField(choices=AppointmentModes.CHOICES)

    start_datetime = models.DateTimeField()  # UTC
    end_datetime = models.DateTimeField()  # UTC

    status = models.CharField(
        max_length=20,
        choices=AppointmentStatus.CHOICES,
        default=AppointmentStatus.PENDING
    )

    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True, editable=False)

    created_by = models.ForeignKey(
        User, null=True, blank=True, related_name='created_appointments',
        on_delete=models.SET_NULL,
    )
    confirmed_by = models.ForeignKey(
        User, null=True, blank=True, related_name='confirmed_appointments',
        on_delete=models.SET_NULL,
    )
    cancelled_by = models.ForeignKey(
        User, null=True, blank=True, related_name='cancelled_appointments',
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ['start_datetime']
        indexes = [
            models.Index(fields=['associate', 'start_datetime']),
            models.Index(fields=['customer', 'start_datetime']),
            models.Index(fields=['status', 'start_datetime']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_datetime__gt=models.F('start_datetime')),
                name='appointment_end_after_start'
            )
        ]

    def __str__(self):
        return f"{self.pk}"


class AppointmentHistory(BaseUUIDModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='history')
    start_datetime = models.DateTimeField()  # UTC
    end_datetime = models.DateTimeField()  # UTC

    reason = models.TextField(blank=True)
    rescheduled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Appointment Histories"

    def __str__(self):
        return f"{self.pk}"
