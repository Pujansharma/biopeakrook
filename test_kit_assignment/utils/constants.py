from django.db import models


class TestKitHandoverType(models.TextChoices):
    DELIVERY = "delivery", "Delivery"
    MANUAL_HANDOVER = "manual_handover", "Manual Handover"


class TestKitAssignmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"
