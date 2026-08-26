from django.db import models


class CenterStatus:
    SETUP = "setup"  # New center, not yet operational
    ACTIVE = "active"  # Fully operational
    INACTIVE = "inactive"  # Temporarily closed
    MAINTENANCE = "maintenance"  # Under maintenance
    PERMANENTLY_CLOSED = "permanently_closed"

    CHOICES = (
        (SETUP, "Setup in Progress"),
        (ACTIVE, "Active"),
        (INACTIVE, "Inactive"),
        (MAINTENANCE, "Under Maintenance"),
        (PERMANENTLY_CLOSED, "Permanently Closed"),
    )


class CenterClosureType(models.TextChoices):
    HOLIDAY = "holiday", "Holiday"
    MANUAL = "manual", "Manual"
