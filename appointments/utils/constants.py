from django.db import models


class AvailabilityGranularity(models.TextChoices):
    DAY = "day", "Day"
    WEEK = "week", "Week"
    MONTH = "month", "Month"


class LeaveScope(models.TextChoices):
    CENTER = "center", "Center"
    ALL_CENTERS = "all_centers", "All Centers"
