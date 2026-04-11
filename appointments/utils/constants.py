from django.db import models


class AppointmentDays(models.TextChoices):
    MONDAY = '0', "Monday"
    TUESDAY = '1', "Tuesday"
    WEDNESDAY = '2', 'Wednesday'
    THURSDAY = '3', 'Thursday'
    FRIDAY = '4', 'Friday'
    SATURDAY = '5', 'Saturday'
    SUNDAY = '6', 'Sunday'


class ScheduleModes(models.TextChoices):
    VIRTUAL = 'virtual', 'Virtual Mode'
    IN_PERSON = "in_person", 'In person mode'
    BOTH = 'both', 'Both'


class AppointmentModes:
    CHOICES = (
        (ScheduleModes.VIRTUAL, "Virtual Mode"),
        (ScheduleModes.IN_PERSON, 'In person mode'),
    )


class AppointmentStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    CANCELLED = 'cancelled', 'Cancelled'
    COMPLETED = 'completed', 'Completed'
    NO_SHOW = 'no_show', 'No Show'

    CHOICES = (
        (PENDING, 'Pending'),
        (CONFIRMED, 'Confirmed'),
        (CANCELLED, 'Cancelled'),
        (COMPLETED, 'Completed'),
        (NO_SHOW, 'No Show'),
    )
