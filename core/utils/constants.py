from django.db import models


class AppointmentDays(models.TextChoices):
    MONDAY = "0", "Monday"
    TUESDAY = "1", "Tuesday"
    WEDNESDAY = "2", "Wednesday"
    THURSDAY = "3", "Thursday"
    FRIDAY = "4", "Friday"
    SATURDAY = "5", "Saturday"
    SUNDAY = "6", "Sunday"


class AppointmentModes(models.TextChoices):
    VIRTUAL = "virtual", "Virtual Mode"
    IN_PERSON = "in_person", "In person mode"
    BOTH = "both", "Both"
