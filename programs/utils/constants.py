from django.db import models


class ProgramType(models.TextChoices):
    WELLNESS = "wellness", "Wellness Programme"


class RedemptionType(models.TextChoices):
    REDEEM = "redeem", "Redeem"
    CANCEL = "cancel", "Cancel"
