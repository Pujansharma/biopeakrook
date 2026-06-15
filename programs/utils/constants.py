from django.db import models


class ProgramType(models.TextChoices):
    THERAPY = "therapy", "Therapy Program"
    ASSESSMENT = "assessment", "Assessment Program"


class RedemptionType(models.TextChoices):
    REDEEM = "redeem", "Redeem"
    CANCEL = "cancel", "Cancel"
